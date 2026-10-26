"""Локальная фаза синхронизации: снимок, сравнение с отслеживаемой веткой и применение чужих изменений.

Всё здесь работает по объектам хранилища и без сети. Вызывающий держит блокировку папки проекта и уводит вызов
в поток, поэтому правки, сборки и снимки не могут вклиниться между чтением HEAD и сдвигом ветки.

* Чужая ветка уже вошла в нашу (или совпала с ней): делать нечего.
* Наша ветка предок чужой: перемотка. Файлы пишутся как есть, новый коммит не создаётся.
* Истории разошлись: план трёх деревьев. Без конфликтов он применяется и закрепляется коммитом слияния с двумя
  родителями. С конфликтами на диск не пишется ничего: сессия (коммиты и отпечаток) остаётся в hse-sync.json.

Запись на диск идёт транзакцией с журналом `kind=sync`: сбой на любом шаге откатывается по копиям файлов
или, если коммит уже сделан, доводится при следующем запуске Студии.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.git_sync.entities import (
    AutoAction,
    ConflictCounts,
    PendingSession,
    SyncAutoChange,
    SyncState,
    SyncWarning,
    TreeEntry,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.merge.entities import MergeAction, MergePlan
from hse_doc_studio.core.git_sync.merge.paths import collision_groups, comparison_key, is_safe_entry, is_safe_path
from hse_doc_studio.core.git_sync.merge.planner import MergeInput, plan_merge, resolve_plan
from hse_doc_studio.core.git_sync.protocols import (
    IFieldResolver,
    IFileMergeStrategy,
    IGitMergeCommitter,
    IGitMergeEngine,
    IGitRepoReader,
    IGitSyncStateRepository,
    MergeMeta,
)
from hse_doc_studio.core.git_sync.remote_project import PROJECT_FILE, require_mergeable_project
from hse_doc_studio.core.template_update.entities import FileWrite, FileWriteKind
from hse_doc_studio.core.template_update.text import is_binary
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.template_update.transaction import SYNC_TRAILER, TemplateUpdateTransaction

logger = structlog.get_logger()

HEADS_PREFIX: Final = "refs/heads/"
TRACKING_PREFIX: Final = "refs/remotes/origin/"
SNAPSHOT_MESSAGE: Final = "Автосохранение перед синхронизацией"
# Замороженные PDF подписей лежат под `.hse-studio/`, но обязаны ехать вместе с проектом.
FROZEN_DIR: Final = ".hse-studio/frozen"
# Сколько автоматических изменений перечисляется в итоге: остальные видны только числом.
MAX_LISTED_AUTO: Final = 200
_STUDIO_PREFIX: Final = ".hse-studio/"


class ApplyKind(StrEnum):
    nothing = "nothing"
    fast_forward = "fast_forward"
    merged = "merged"
    conflicts = "conflicts"


@dataclass(frozen=True)
class ApplyOutcome:
    kind: ApplyKind
    # Сколько коммитов пришло с чужой стороны.
    pulled: int = 0
    merge_commit: str | None = None
    files_changed: int = 0
    auto: tuple[SyncAutoChange, ...] = ()
    warnings: tuple[SyncWarning, ...] = ()
    conflicts: ConflictCounts | None = None


class HeadMovedError(Exception):
    """Ветка успела сдвинуться между чтением и записью: вызывающий начинает локальную фазу заново."""


def _tracking_ref(state: SyncState) -> str:
    return f"{TRACKING_PREFIX}{state.remote_branch}"


class SyncApplier:
    def __init__(
        self,
        *,
        vcs: IVcsService,
        reader: IGitRepoReader,
        committer: IGitMergeCommitter,
        transaction: TemplateUpdateTransaction,
        states: IGitSyncStateRepository,
        engine: IGitMergeEngine,
        structured: IFileMergeStrategy,
        resolver: IFieldResolver,
    ) -> None:
        self._vcs = vcs
        self._reader = reader
        self._committer = committer
        self._transaction = transaction
        self._states = states
        self._engine = engine
        self._structured = structured
        self._resolver = resolver

    def snapshot(self, project: Project) -> None:
        """Всё, что человек успел изменить, попадает в историю: уйти на сервер может только закоммитенное."""
        settings = VcsSettings.from_meta(project.meta)
        self._vcs.commit(
            project,
            message=SNAPSHOT_MESSAGE,
            kind=VcsCommitKind.manual,
            include_pdf=settings.track_pdf,
            force_paths=[FROZEN_DIR],
        )

    def apply(self, project: Project, state: SyncState, sync_id: str) -> ApplyOutcome:
        """Снимок и применение чужой ветки. Бросает HeadMovedError, если ветка сдвинулась под ногами."""
        folder = project.folder
        self.snapshot(project)
        branch = state.local_branch
        if self._reader.current_branch(folder) != branch:
            raise git_error(GitErrorCode.off_branch)
        ours = self._reader.rev_parse(folder, f"{HEADS_PREFIX}{branch}")
        if ours is None:
            raise git_error(GitErrorCode.branch_missing)
        theirs = self._reader.rev_parse(folder, _tracking_ref(state))
        if theirs is None or theirs == ours or self._reader.is_ancestor(folder, theirs, ours):
            if state.pending is not None:
                # Чужая ветка уже вошла в нашу другим путём: сессия конфликтов потеряла смысл.
                self._states.save(folder, replace(state, pending=None))
            return ApplyOutcome(ApplyKind.nothing)
        self.ensure_remote_mergeable(project, theirs)
        pulled = self._reader.count_commits(folder, f"{ours}..{theirs}")
        if self._reader.is_ancestor(folder, ours, theirs):
            outcome = self._fast_forward(project, state, ours, theirs, pulled, sync_id)
            if outcome is not None:
                return outcome
        return self._merge(project, state, ours, theirs, pulled, sync_id)

    def ensure_remote_mergeable(self, project: Project, theirs: str) -> None:
        raw = self._reader.read_files(project.folder, theirs, [PROJECT_FILE]).get(PROJECT_FILE)
        require_mergeable_project(raw, project.id)

    # --- перемотка ---------------------------------------------------------------------------------------------

    def _fast_forward(
        self, project: Project, state: SyncState, ours: str, theirs: str, pulled: int, sync_id: str
    ) -> ApplyOutcome | None:
        """None: перемотать нельзя (небезопасные или совпадающие по имени пути), нужен коммит слияния."""
        folder = project.folder
        changed = self._reader.changed_paths(folder, ours, theirs)
        entries = {entry.path: entry for entry in self._reader.tree_entries(folder, theirs)}
        if not _can_fast_forward(changed, entries):
            return None
        wanted = [path for status, path in changed if status != "D"]
        contents = self._reader.read_files(folder, theirs, wanted)
        writes: list[FileWrite] = []
        for status, path in changed:
            if status == "D":
                writes.append(FileWrite(path, FileWriteKind.delete))
            elif (data := contents.get(path)) is not None:
                writes.append(FileWrite(path, FileWriteKind.write, data))
            else:
                return None

        def commit() -> str:
            if not self._committer.fast_forward(folder, state.local_branch, expected=ours, new=theirs):
                raise HeadMovedError
            return theirs

        self._write(project, state, ours, theirs, sync_id, writes, commit)
        auto = tuple(
            SyncAutoChange(w.path, AutoAction.delete if w.kind is FileWriteKind.delete else AutoAction.take_theirs)
            for w in writes[:MAX_LISTED_AUTO]
        )
        return ApplyOutcome(ApplyKind.fast_forward, pulled=pulled, files_changed=len(writes), auto=auto)

    # --- слияние -----------------------------------------------------------------------------------------------

    def _merge(
        self, project: Project, state: SyncState, ours: str, theirs: str, pulled: int, sync_id: str
    ) -> ApplyOutcome:
        folder = project.folder
        base = self._reader.merge_base(folder, ours, theirs)
        if base is None and not state.adopted_unrelated:
            raise git_error(GitErrorCode.unrelated_histories, can_adopt=True)
        theirs_entries = {entry.path: entry for entry in self._reader.tree_entries(folder, theirs)}
        paths = self._merge_paths(folder, base, ours, theirs, theirs_entries)
        merge_input = self._merge_input(folder, base, ours, theirs, paths, theirs_entries)
        plan = plan_merge(merge_input, self._engine, self._structured)
        if plan.conflicts:
            return self._keep_conflicts(project, state, ours, theirs, base, plan)
        writes = resolve_plan(plan, {}, self._resolver)
        changes: dict[str, bytes | None] = {
            w.path: w.content if w.kind is FileWriteKind.write else None for w in writes
        }
        message = f"Синхронизация: слияние с {state.remote_branch} ({theirs[:7]})"

        def commit() -> str:
            merged = self._committer.commit_merge(
                folder, ours=ours, theirs=theirs, changes=changes, message=message, trailers={SYNC_TRAILER: sync_id}
            )
            if not self._committer.advance_branch(folder, state.local_branch, expected=ours, new=merged):
                raise HeadMovedError
            return merged

        merge_commit = self._write(project, state, ours, theirs, sync_id, writes, commit)
        return ApplyOutcome(
            ApplyKind.merged,
            pulled=pulled,
            merge_commit=merge_commit,
            files_changed=len(writes),
            auto=_auto_changes(plan),
            warnings=plan.warnings,
        )

    def _merge_paths(
        self, folder: Path, base: str | None, ours: str, theirs: str, theirs_entries: Mapping[str, TreeEntry]
    ) -> list[str]:
        """Пути, которые изменила чужая сторона: для остальных слияние ничего не меняет, читать их незачем.

        К ним добавляются мои пути, совпадающие с ними по имени без учёта регистра и NFC: иначе столкновение
        имён на регистронезависимых файловых системах планировщик не увидел бы.
        """
        if base is None:
            paths = set(theirs_entries)
        else:
            paths = {path for _, path in self._reader.changed_paths(folder, base, theirs)}
        mine: dict[str, list[str]] = {}
        for entry in self._reader.tree_entries(folder, ours):
            mine.setdefault(comparison_key(entry.path), []).append(entry.path)
        for path in tuple(paths):
            paths.update(mine.get(comparison_key(path), ()))
        return sorted(paths)

    def _merge_input(
        self,
        folder: Path,
        base: str | None,
        ours: str,
        theirs: str,
        paths: Sequence[str],
        theirs_entries: Mapping[str, TreeEntry],
    ) -> MergeInput:
        base_files = _present(self._reader.read_files(folder, base, paths)) if base else {}
        ours_files = _present(self._reader.read_files(folder, ours, paths))
        theirs_files = _present(self._reader.read_files(folder, theirs, paths))
        blocked = frozenset(
            path for path in paths if path in theirs_entries and not is_safe_entry(path, theirs_entries[path].mode)
        )
        return MergeInput(
            base=base_files,
            ours=ours_files,
            theirs=theirs_files,
            base_commit=base,
            theirs_commit=theirs,
            meta=self._meta(folder, base, ours, theirs, base_files, ours_files, theirs_files),
            blocked=blocked,
        )

    def _meta(
        self,
        folder: Path,
        base: str | None,
        ours: str,
        theirs: str,
        base_files: Mapping[str, bytes],
        ours_files: Mapping[str, bytes],
        theirs_files: Mapping[str, bytes],
    ) -> dict[str, MergeMeta]:
        """Кто правил файл позже: нужно бинарникам и файлам состояния, где побеждает более новая правка."""
        both = {path for path in theirs_files.keys() & ours_files.keys() if base_files.get(path) != ours_files[path]}
        meta: dict[str, MergeMeta] = {}
        for path in sorted(both):
            if not _needs_stamps(path, base_files.get(path), ours_files[path], theirs_files[path]):
                continue
            mine = self._reader.path_stamp(folder, ours, path, exclude_reachable_from=base)
            other = self._reader.path_stamp(folder, theirs, path, exclude_reachable_from=base)
            meta[path] = MergeMeta(
                ours_changed_at=mine.committed_at if mine else None,
                theirs_changed_at=other.committed_at if other else None,
                ours_commit=mine.sha if mine else None,
                theirs_commit=other.sha if other else None,
            )
        return meta

    def _keep_conflicts(
        self, project: Project, state: SyncState, ours: str, theirs: str, base: str | None, plan: MergePlan
    ) -> ApplyOutcome:
        """Конфликты решает человек: на диск ничего не пишется, сессия остаётся рядом с хранилищем."""
        previous = state.pending
        same = previous is not None and previous.fingerprint == plan.fingerprint
        session_id = previous.session_id if previous is not None and same else uuid.uuid4().hex[:12]
        total = len(plan.conflicts)
        pending = PendingSession(
            session_id=session_id,
            files_total=total,
            files_open=previous.files_open if previous is not None and same else total,
            ours=ours,
            theirs=theirs,
            base=base,
            fingerprint=plan.fingerprint,
        )
        self._states.save(project.folder, replace(state, pending=pending))
        logger.info("git sync stopped on conflicts", project_id=str(project.id), files=total, session=session_id)
        return ApplyOutcome(
            ApplyKind.conflicts,
            auto=_auto_changes(plan),
            warnings=plan.warnings,
            conflicts=ConflictCounts(files_total=total, files_open=pending.files_open),
        )

    # --- запись на диск ----------------------------------------------------------------------------------------

    def _write(
        self,
        project: Project,
        state: SyncState,
        ours: str,
        theirs: str,
        sync_id: str,
        writes: Sequence[FileWrite],
        commit: Callable[[], str],
    ) -> str | None:
        """Транзакция с журналом: копии, запись файлов, коммит. Возвращает коммит слияния (None при перемотке)."""
        folder = project.folder
        aside = self._set_aside_untracked(project, ours, writes)
        journal = self._transaction.start_sync_journal(pre_commit=ours, merge_parent=theirs, sync_id=sync_id)

        def save_state() -> None:
            self._states.save(folder, replace(state, pending=None, adopted_unrelated=False))

        result = self._transaction.run(project, journal, [*writes, *aside], save_state=save_state, commit=commit)
        return result if result != theirs else None

    def _set_aside_untracked(self, project: Project, ours: str, writes: Sequence[FileWrite]) -> list[FileWrite]:
        """Чужой файл ложится на место неотслеживаемого (например, PDF, который у меня в исключениях).

        Мой файл не пропадает: он переезжает рядом под именем `<имя>.local<расширение>`. Эти копии в историю
        не идут: имя попадает под те же исключения, что и оригинал, а откат журнала их убирает.
        """
        folder = project.folder
        incoming = [w for w in writes if w.kind is FileWriteKind.write]
        tracked = self._reader.read_files(folder, ours, [w.path for w in incoming])
        taken = {w.path for w in writes}
        moved: list[FileWrite] = []
        for write in incoming:
            target = folder / write.path
            if tracked.get(write.path) is not None or target.is_symlink() or not target.is_file():
                continue
            local = target.read_bytes()
            if local == write.content:
                continue
            copy = _local_copy_name(write.path, taken, folder)
            taken.add(copy)
            moved.append(FileWrite(copy, FileWriteKind.write, local))
        return moved


def _present(files: Mapping[str, bytes | None]) -> dict[str, bytes]:
    return {path: data for path, data in files.items() if data is not None}


def _needs_stamps(path: str, *contents: bytes | None) -> bool:
    if path.lower().endswith(".pdf") or is_binary(path, *contents):
        return True
    return path.startswith(_STUDIO_PREFIX) and path.endswith(".json")


def _auto_changes(plan: MergePlan) -> tuple[SyncAutoChange, ...]:
    listed = [
        SyncAutoChange(op.path, AutoAction(op.action.value), op.copy_path)
        for op in plan.ops
        if op.action is not MergeAction.conflict
    ]
    return tuple(listed[:MAX_LISTED_AUTO])


def _can_fast_forward(changed: Sequence[tuple[str, str]], entries: Mapping[str, TreeEntry]) -> bool:
    """Перемотка берёт дерево чужой ветки целиком, поэтому годится, только если в нём нечего отбрасывать."""
    touched = {path for _, path in changed}
    if not all(is_safe_path(path) for path in touched):
        return False
    present = [path for status, path in changed if status != "D"]
    if any(path not in entries or not is_safe_entry(path, entries[path].mode) for path in present):
        return False
    return not any(touched.intersection(group) for group in collision_groups(entries))


def _local_copy_name(path: str, taken: set[str], folder: Path) -> str:
    posix = PurePosixPath(path)
    for number in range(1, 1000):
        marker = ".local" if number == 1 else f".local{number}"
        candidate = str(posix.with_name(f"{posix.stem}{marker}{posix.suffix}"))
        if candidate not in taken and not (folder / candidate).exists():
            return candidate
    return str(posix.with_name(f"{posix.stem}.local-{uuid.uuid4().hex[:6]}{posix.suffix}"))
