"""Локальная фаза синхронизации: снимок, сравнение с отслеживаемой веткой и применение чужих изменений.

Всё здесь работает по объектам хранилища и без сети. Вызывающий держит блокировку папки проекта и уводит вызов
в поток, поэтому правки, сборки и снимки не могут вклиниться между чтением HEAD и сдвигом ветки.

* Чужая ветка уже вошла в нашу (или совпала с ней): делать нечего.
* Наша ветка предок чужой: перемотка. Файлы пишутся как есть, новый коммит не создаётся.
* Истории разошлись: план трёх деревьев. Без конфликтов он применяется и закрепляется коммитом слияния с двумя
  родителями. С конфликтами на диск не пишется ничего: сессия (коммиты и отпечаток) остаётся в hse-sync.json.

Те же шаги выполняются для ветки из переносного файла (`theirs_ref=refs/hse/bundle/<ветка>`): она занимает место
отслеживаемой ветки, всё остальное, включая конфликты и решения по ним, общее.

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
from hse_doc_studio.core.git_sync.error_messages import git_error, localized_resolution_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.merge.choices import FileChoice, FileResolution
from hse_doc_studio.core.git_sync.merge.drafts import progress, prune_all
from hse_doc_studio.core.git_sync.merge.entities import MergeAction, MergePlan
from hse_doc_studio.core.git_sync.merge.paths import collision_groups, is_safe_entry, is_safe_path
from hse_doc_studio.core.git_sync.merge.planner import resolve_plan
from hse_doc_studio.core.git_sync.merge.signature_groups import conflicting_groups, group_paths, sides_of
from hse_doc_studio.core.git_sync.protocols import (
    IFieldResolver,
    IGitMergeCommitter,
    IGitRepoReader,
    IGitSyncStateRepository,
    IRemoteProjectCheck,
)
from hse_doc_studio.core.git_sync.refs import BUNDLE_PREFIX
from hse_doc_studio.core.git_sync.remote_project import PROJECT_FILE, require_mergeable_project
from hse_doc_studio.core.template_update.entities import FileWrite, FileWriteKind
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.git_sync.conflict_plan import ConflictPlanner
from hse_doc_studio.use_cases.template_update.transaction import SYNC_TRAILER, TemplateUpdateTransaction

logger = structlog.get_logger()

HEADS_PREFIX: Final = "refs/heads/"
TRACKING_PREFIX: Final = "refs/remotes/origin/"
SNAPSHOT_MESSAGE: Final = "Автосохранение перед синхронизацией"
# Замороженные PDF подписей лежат под `.hse-studio/`, но обязаны ехать вместе с проектом.
FROZEN_DIR: Final = ".hse-studio/frozen"
# Сколько автоматических изменений перечисляется в итоге: остальные видны только числом.
MAX_LISTED_AUTO: Final = 200


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


@dataclass(frozen=True)
class ResolveRequest:
    """Решения человека по конфликтам и отпечаток плана, на котором он их принимал."""

    fingerprint: str
    resolutions: Mapping[str, FileResolution]
    push: bool = True


class HeadMovedError(Exception):
    """Ветка успела сдвинуться между чтением и записью: вызывающий начинает локальную фазу заново."""


def _tracking_ref(state: SyncState) -> str:
    return f"{TRACKING_PREFIX}{state.remote_branch}"


def _session_ref(state: SyncState) -> str:
    """Чужая сторона открытой сессии конфликтов: ветка из файла или отслеживаемая ветка сервера."""
    return state.pending.theirs_ref if state.pending is not None and state.pending.theirs_ref else _tracking_ref(state)


class SyncApplier:
    def __init__(
        self,
        *,
        vcs: IVcsService,
        reader: IGitRepoReader,
        committer: IGitMergeCommitter,
        transaction: TemplateUpdateTransaction,
        states: IGitSyncStateRepository,
        planner: ConflictPlanner,
        resolver: IFieldResolver,
        project_check: IRemoteProjectCheck,
    ) -> None:
        self._vcs = vcs
        self._reader = reader
        self._committer = committer
        self._transaction = transaction
        self._states = states
        self._planner = planner
        self._resolver = resolver
        self._project_check = project_check

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

    def apply(self, project: Project, state: SyncState, sync_id: str, theirs_ref: str | None = None) -> ApplyOutcome:
        """Снимок и применение чужой ветки. Бросает HeadMovedError, если ветка сдвинулась под ногами.

        `theirs_ref`: ссылка на ветку из переносного файла; без неё применяется отслеживаемая ветка сервера.
        Ссылка файла после применения без конфликтов убирается: она нужна только пока идёт слияние.
        """
        outcome = self._apply(project, state, sync_id, theirs_ref)
        if theirs_ref is not None and outcome.kind is not ApplyKind.conflicts:
            self._committer.delete_ref(project.folder, theirs_ref)
        return outcome

    def _apply(self, project: Project, state: SyncState, sync_id: str, theirs_ref: str | None) -> ApplyOutcome:
        folder = project.folder
        self.snapshot(project)
        branch = state.local_branch
        if self._reader.current_branch(folder) != branch:
            raise git_error(GitErrorCode.off_branch)
        ours = self._reader.rev_parse(folder, f"{HEADS_PREFIX}{branch}")
        if ours is None:
            raise git_error(GitErrorCode.branch_missing)
        theirs = self._reader.rev_parse(folder, theirs_ref or _tracking_ref(state))
        if theirs is None or theirs == ours or self._reader.is_ancestor(folder, theirs, ours):
            if state.pending is not None and state.pending.theirs_ref == theirs_ref:
                # Чужая ветка уже вошла в нашу другим путём: сессия конфликтов потеряла смысл.
                self._states.save(folder, replace(state, pending=None))
            return ApplyOutcome(ApplyKind.nothing)
        self.ensure_remote_mergeable(project, theirs)
        pulled = self._reader.count_commits(folder, f"{ours}..{theirs}")
        if self._reader.is_ancestor(folder, ours, theirs):
            outcome = self._fast_forward(project, state, ours, theirs, pulled, sync_id)
            if outcome is not None:
                return outcome
        return self._merge(project, state, ours, theirs, pulled, sync_id, theirs_ref)

    def ensure_remote_mergeable(self, project: Project, theirs: str) -> None:
        raw = self._reader.read_files(project.folder, theirs, [PROJECT_FILE]).get(PROJECT_FILE)
        require_mergeable_project(raw, project.id, self._project_check)

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
        self,
        project: Project,
        state: SyncState,
        ours: str,
        theirs: str,
        pulled: int,
        sync_id: str,
        theirs_ref: str | None,
    ) -> ApplyOutcome:
        plan = self._planner.plan(project.folder, ours, theirs, adopted_unrelated=state.adopted_unrelated)
        if plan.conflicts:
            return self._keep_conflicts(project, state, ours, theirs, plan, theirs_ref)
        writes = resolve_plan(plan, {}, self._resolver)
        message = _merge_title(state, theirs, theirs_ref)
        return self._commit_merge(project, state, ours, theirs, pulled, sync_id, plan, writes, message)

    def _commit_merge(
        self,
        project: Project,
        state: SyncState,
        ours: str,
        theirs: str,
        pulled: int,
        sync_id: str,
        plan: MergePlan,
        writes: Sequence[FileWrite],
        message: str,
    ) -> ApplyOutcome:
        folder = project.folder
        changes: dict[str, bytes | None] = {
            w.path: w.content if w.kind is FileWriteKind.write else None for w in writes
        }

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

    # --- применение решений человека ---------------------------------------------------------------------------

    def check_resolution(self, project: Project, state: SyncState, request: ResolveRequest) -> None:
        """Всё, что может отказать до запуска операции: устаревший план, неполные или недопустимые решения."""
        self.snapshot(project)
        heads = self._heads(project, state)
        if heads is None or self._is_moot(project, heads):
            return
        self._resolved_writes(project, state, heads[0], heads[1], request)

    def apply_resolved(self, project: Project, state: SyncState, sync_id: str, request: ResolveRequest) -> ApplyOutcome:
        """Слияние с решениями человека. Сессия, потерявшая смысл (чужая ветка уже вошла в нашу), идёт обычным путём."""
        self.snapshot(project)
        heads = self._heads(project, state)
        theirs_ref = state.pending.theirs_ref if state.pending is not None else None
        if heads is None or self._is_moot(project, heads):
            return self.apply(project, state, sync_id, theirs_ref)
        ours, theirs = heads
        self.ensure_remote_mergeable(project, theirs)
        plan, writes = self._resolved_writes(project, state, ours, theirs, request)
        pulled = self._reader.count_commits(project.folder, f"{ours}..{theirs}")
        message = f"{_merge_title(state, theirs, theirs_ref)}, конфликты решены"
        outcome = self._commit_merge(project, state, ours, theirs, pulled, sync_id, plan, writes, message)
        if theirs_ref is not None:
            self._committer.delete_ref(project.folder, theirs_ref)
        return outcome

    def _heads(self, project: Project, state: SyncState) -> tuple[str, str] | None:
        folder = project.folder
        if self._reader.current_branch(folder) != state.local_branch:
            raise git_error(GitErrorCode.off_branch)
        ours = self._reader.rev_parse(folder, f"{HEADS_PREFIX}{state.local_branch}")
        if ours is None:
            raise git_error(GitErrorCode.branch_missing)
        theirs = self._reader.rev_parse(folder, _session_ref(state))
        return None if theirs is None else (ours, theirs)

    def _is_moot(self, project: Project, heads: tuple[str, str]) -> bool:
        """Расхождения уже нет: чужая ветка вошла в нашу или наша целиком лежит в чужой."""
        ours, theirs = heads
        folder = project.folder
        return (
            theirs == ours
            or self._reader.is_ancestor(folder, theirs, ours)
            or self._reader.is_ancestor(folder, ours, theirs)
        )

    def _resolved_writes(
        self, project: Project, state: SyncState, ours: str, theirs: str, request: ResolveRequest
    ) -> tuple[MergePlan, list[FileWrite]]:
        plan = self._planner.plan(project.folder, ours, theirs, adopted_unrelated=state.adopted_unrelated)
        if plan.fingerprint != request.fingerprint:
            raise git_error(GitErrorCode.plan_outdated)
        try:
            writes = resolve_plan(plan, request.resolutions, self._resolver)
        except GitSyncError as exc:
            raise localized_resolution_error(exc) from exc
        return plan, self._follow_signature_groups(project.folder, plan, request.resolutions, writes, ours, theirs)

    def _follow_signature_groups(
        self,
        folder: Path,
        plan: MergePlan,
        resolutions: Mapping[str, FileResolution],
        writes: list[FileWrite],
        ours: str,
        theirs: str,
    ) -> list[FileWrite]:
        """Замороженный PDF и подписи к нему идут за решением по группе, а не за новизной каждого файла."""
        groups = conflicting_groups(plan)
        if not groups:
            return writes
        chosen = sides_of(groups, resolutions)
        affected = group_paths(plan)
        kept = [w for w in writes if w.path not in affected]
        for group in groups:
            if chosen.get(group.doc_id) is not FileChoice.theirs:
                continue
            incoming = self._reader.read_files(folder, theirs, sorted(group.theirs))
            kept.extend(
                FileWrite(path, FileWriteKind.write, data) for path, data in incoming.items() if data is not None
            )
            stale = sorted(group.ours - group.theirs)
            present = self._reader.read_files(folder, ours, stale) if stale else {}
            kept.extend(FileWrite(path, FileWriteKind.delete) for path, data in present.items() if data is not None)
        return kept

    def _keep_conflicts(
        self, project: Project, state: SyncState, ours: str, theirs: str, plan: MergePlan, theirs_ref: str | None
    ) -> ApplyOutcome:
        """Конфликты решает человек: на диск ничего не пишется, сессия остаётся рядом с хранилищем.

        Черновики прежней сессии переходят в новую по ключам участков и полей, поэтому новая выборка не стирает
        то, что человек уже решил.
        """
        previous = state.pending
        same = previous is not None and previous.fingerprint == plan.fingerprint
        session_id = previous.session_id if previous is not None and same else uuid.uuid4().hex[:12]
        drafts = prune_all({op.path: op for op in plan.conflicts}, previous.drafts) if previous is not None else {}
        total = len(plan.conflicts)
        left = sum(not progress(op, drafts.get(op.path)).resolved for op in plan.conflicts)
        pending = PendingSession(
            session_id=session_id,
            files_total=total,
            files_open=left,
            ours=ours,
            theirs=theirs,
            base=plan.base_commit,
            fingerprint=plan.fingerprint,
            drafts=drafts,
            drafts_saved_at=previous.drafts_saved_at if previous is not None and drafts else None,
            theirs_ref=theirs_ref,
        )
        self._states.save(project.folder, replace(state, pending=pending))
        logger.info("git sync stopped on conflicts", project_id=str(project.id), files=total, session=session_id)
        return ApplyOutcome(
            ApplyKind.conflicts,
            auto=_auto_changes(plan),
            warnings=plan.warnings,
            conflicts=ConflictCounts(files_total=total, files_open=left),
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


def _merge_title(state: SyncState, theirs: str, theirs_ref: str | None) -> str:
    if theirs_ref is not None and theirs_ref.startswith(BUNDLE_PREFIX):
        return f"Импорт из файла: слияние с {theirs_ref.removeprefix(BUNDLE_PREFIX)} ({theirs[:7]})"
    return f"Синхронизация: слияние с {state.remote_branch} ({theirs[:7]})"


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
