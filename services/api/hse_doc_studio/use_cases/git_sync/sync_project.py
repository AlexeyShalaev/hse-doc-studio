"""Синхронизация проекта с удалённым репозиторием: снимок, выборка, применение чужих изменений, отправка.

Блокировка папки проекта (IVcsFolderLocks) держится только на локальных фазах: снимок и применение. Сеть
(выборка и отправка) идёт без неё, поэтому правки и сборки не ждут медленный сервер. Правки, сделанные за время
сети, не теряются: применение снова делает снимок под блокировкой, а отправляется закреплённый коммит.

Фазы операции: queued (ждём окончания сборки) -> snapshot -> fetch -> merge -> push. Если за время отправки
сервер успел получить чужие коммиты (`remote_moved`), цикл повторяется с выборки, не больше трёх раз.
Конфликты слияния не ошибка: операция заканчивается итогом `conflicts`, а сессия остаётся в hse-sync.json.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.entities import (
    GitOperationError,
    LastSync,
    OperationPhase,
    OperationStatus,
    RemoteTarget,
    SyncAutoChange,
    SyncHealth,
    SyncOutcome,
    SyncResult,
    SyncState,
    SyncWarning,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.fetch_schedule import FetchBook
from hse_doc_studio.core.git_sync.merge.text import has_hse_markers
from hse_doc_studio.core.git_sync.policy import DEFAULT_REMOTE_BRANCH, GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IGitOperationRegistry,
    IGitRepoReader,
    IGitStoreRemotes,
    IGitSyncStateRepository,
    IGitTransport,
)
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.template_update.text import is_binary
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks
from hse_doc_studio.use_cases.git_sync.health import with_failure, with_success
from hse_doc_studio.use_cases.git_sync.status import default_state
from hse_doc_studio.use_cases.git_sync.sync_apply import (
    HEADS_PREFIX,
    TRACKING_PREFIX,
    ApplyKind,
    ApplyOutcome,
    HeadMovedError,
    ResolveRequest,
    SyncApplier,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

# Сколько раз цикл «выборка, применение, отправка» повторяется, если сервер ушёл вперёд во время отправки.
MAX_PUSH_ATTEMPTS: Final = 3
# Сколько раз применение начинается заново, если ветка сдвинулась под ногами.
MAX_APPLY_ATTEMPTS: Final = 3
# Сколько ждём окончания идущей сборки перед применением и как часто проверяем.
BUILD_WAIT_S: float = 120.0
BUILD_POLL_S: float = 0.5
# Файлы крупнее не ищутся на маркеры конфликтов: это не текст, который правит человек.
_MARKER_SCAN_LIMIT: Final = 2_000_000
_MARKER_BATCH: Final = 200
_MAX_LISTED_PATHS: Final = 20


@dataclass
class _Totals:
    """Что набралось за все круги цикла."""

    pulled: int = 0
    pushed: int = 0
    merge_commit: str | None = None
    fast_forwarded: bool = False
    files_changed: int = 0
    auto: list[SyncAutoChange] = field(default_factory=list)
    warnings: list[SyncWarning] = field(default_factory=list)

    def add(self, applied: ApplyOutcome) -> None:
        self.pulled += applied.pulled
        self.files_changed += applied.files_changed
        self.auto.extend(applied.auto)
        self.warnings.extend(applied.warnings)
        if applied.kind is ApplyKind.merged:
            self.merge_commit = applied.merge_commit
        elif applied.kind is ApplyKind.fast_forward:
            self.fast_forwarded = True

    def outcome(self) -> SyncOutcome:
        if self.merge_commit is not None:
            return SyncOutcome.merged
        if self.fast_forwarded:
            return SyncOutcome.fast_forwarded
        return SyncOutcome.pushed if self.pushed else SyncOutcome.up_to_date


def _now() -> datetime:
    return datetime.now(UTC)


class SyncProjectUC:
    """Выполняет синхронизацию уже начатой операции; ошибки оседают в операции, а не летят наружу."""

    def __init__(
        self,
        *,
        get_project: GetProjectUC,
        applier: SyncApplier,
        reader: IGitRepoReader,
        transport: IGitTransport,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        operations: IGitOperationRegistry,
        locks: IVcsFolderLocks,
        dispatcher: IJobDispatcher,
        policy: GitSyncPolicy,
        fetch_book: FetchBook,
    ) -> None:
        self._get_project = get_project
        self._applier = applier
        self._reader = reader
        self._transport = transport
        self._remotes = store_remotes
        self._states = state_repo
        self._operations = operations
        self._locks = locks
        self._dispatcher = dispatcher
        self._policy = policy
        self._fetch_book = fetch_book

    async def run(self, project: Project, operation_id: str, resolve: ResolveRequest | None = None) -> None:
        """Итог (успех, сбой, отмена) записывается в операцию. Наружу выходит только CancelledError.

        С `resolve` первый круг применяет решения человека по конфликтам вместо выборки: чужая вершина остаётся
        той, на которой он решал. Дальше (отправка, повтор после `remote_moved`) всё как при обычной синхронизации.
        """
        try:
            result = await self._execute(project, operation_id, uuid.uuid4().hex[:12], resolve)
        except asyncio.CancelledError:
            self._operations.finish(operation_id, status=OperationStatus.cancelled)
            raise
        except GitSyncError as exc:
            self._operations.finish(
                operation_id, status=OperationStatus.failed, error=GitOperationError(exc.code, exc.detail)
            )
        except Exception:
            logger.exception("git sync failed", project_id=str(project.id))
            self._operations.finish(
                operation_id,
                status=OperationStatus.failed,
                error=GitOperationError(GitErrorCode.git_error, git_error(GitErrorCode.git_error).detail),
            )
        else:
            self._operations.finish(operation_id, result=result)

    # --- цикл -------------------------------------------------------------------------------------------------

    async def import_ref(self, project: Project, operation_id: str, sync_id: str, theirs_ref: str) -> ApplyOutcome:
        """Локальная фаза синхронизации для ветки, которая уже лежит в `theirs_ref` (переносной файл).

        Те же ожидание сборок, блокировка папки, снимок, план и применение, что у обычной синхронизации,
        но без выборки и отправки: файл не требует ни сети, ни подключённого репозитория.
        """
        return await self._apply(project, operation_id, sync_id, None, theirs_ref)

    async def _execute(
        self, project: Project, operation_id: str, sync_id: str, resolve: ResolveRequest | None = None
    ) -> SyncResult:
        # Решения без отправки (слияние с файлом) обходятся без сервера: адрес подключения может и не быть.
        local = resolve is not None and not resolve.push
        target = None if local else await asyncio.to_thread(self._target, project)
        totals = _Totals()
        for attempt in range(MAX_PUSH_ATTEMPTS):
            project = (await self._get_project.execute(GetProjectInput(project_id=project.id))).project
            resolving = resolve if attempt == 0 else None
            await self._refresh(project, target, operation_id, first=attempt == 0, resolving=resolving is not None)
            applied = await self._apply(project, operation_id, sync_id, resolving)
            totals.add(applied)
            if applied.kind is ApplyKind.conflicts:
                return await self._finish(project, sync_id, totals, SyncOutcome.conflicts, applied)
            if resolving is not None and not resolving.push:
                return await self._finish(project, sync_id, totals, totals.outcome(), applied)
            assert target is not None  # noqa: S101 — без цели сюда приходят только решения без отправки, они вышли выше
            try:
                totals.pushed += await self._push(project, target, operation_id)
            except GitSyncError as exc:
                if exc.code is not GitErrorCode.remote_moved or attempt == MAX_PUSH_ATTEMPTS - 1:
                    await self._record_failure(project, exc, fetch=False)
                    raise
                continue
            return await self._finish(project, sync_id, totals, totals.outcome(), applied)
        raise git_error(GitErrorCode.remote_moved)

    async def _refresh(
        self, project: Project, target: RemoteTarget | None, operation_id: str, *, first: bool, resolving: bool
    ) -> None:
        """Снимок и выборка перед применением. Решения по конфликтам применяются к уже известной чужой вершине."""
        if resolving or target is None:
            return
        if first:
            await self._snapshot(project, operation_id)
        await self._fetch(project, target, operation_id)

    def _target(self, project: Project) -> RemoteTarget:
        config = self._remotes.read(project)
        if config is None:
            raise git_error(GitErrorCode.not_a_studio_project)
        state = self._states.get(project.folder) or default_state(config, None)
        url = parse_remote_url(
            config.url, allow_http=self._policy.allow_insecure_http, allow_local=self._policy.allow_local_remotes
        )
        return RemoteTarget(
            url, state.credential_id or config.credential_id, insecure_http=state.insecure_http, project_id=project.id
        )

    def _load_state(self, project: Project) -> SyncState:
        config = self._remotes.read(project)
        state = self._states.get(project.folder)
        if state is not None:
            return state
        if config is None:
            raise git_error(GitErrorCode.not_a_studio_project)
        return default_state(config, None)

    def _local_state(self, project: Project) -> SyncState:
        """Состояние проекта, у которого может не быть ни подключения, ни hse-sync.json: ветка берётся с HEAD."""
        state = self._states.get(project.folder)
        if state is not None:
            return state
        current = self._reader.current_branch(project.folder)
        config = self._remotes.read(project)
        if config is not None:
            return default_state(config, current)
        branch = current or DEFAULT_REMOTE_BRANCH
        return SyncState(local_branch=branch, remote_branch=branch)

    async def _update_state(self, project: Project, change: Callable[[SyncState], SyncState]) -> None:
        """Состояние меняется под блокировкой папки: так оно не расходится с записями применения."""
        async with self._locks.for_folder(project.folder):
            await asyncio.to_thread(lambda: self._states.save(project.folder, change(self._load_state(project))))

    async def _record_failure(self, project: Project, exc: GitSyncError, *, fetch: bool) -> None:
        try:
            await self._update_state(project, lambda state: with_failure(state, exc, at=_now(), fetch=fetch))
        except Exception:  # noqa: BLE001 — запись здоровья вторична, основная ошибка важнее
            logger.warning("git sync: failure was not recorded", project_id=str(project.id), exc_info=True)

    # --- фазы -------------------------------------------------------------------------------------------------

    def _phase(self, operation_id: str, phase: OperationPhase, *, cancellable: bool) -> None:
        self._operations.update(operation_id, phase=phase, percent=None, cancellable=cancellable)

    async def _snapshot(self, project: Project, operation_id: str) -> None:
        self._phase(operation_id, OperationPhase.snapshot, cancellable=False)
        async with self._locks.for_folder(project.folder):
            await asyncio.to_thread(self._applier.snapshot, project)

    async def _fetch(self, project: Project, target: RemoteTarget, operation_id: str) -> None:
        self._phase(operation_id, OperationPhase.fetch, cancellable=True)
        state = await asyncio.to_thread(self._load_state, project)
        git_dir = self._remotes.git_dir(project)
        try:
            # Фоновая выборка, начатая до синхронизации, ещё может идти: две выборки в одну ссылку мешают друг
            # другу (cannot lock ref), поэтому ждём её конца и только потом обновляем ссылку сами.
            async with self._fetch_book.lock(project.folder):
                await self._transport.fetch(
                    git_dir,
                    target,
                    branch=state.remote_branch,
                    on_progress=lambda percent, _line: self._operations.update(operation_id, percent=percent),
                )
        except GitSyncError as exc:
            if exc.code is GitErrorCode.branch_missing and state.remote_empty:
                # Репозиторий всё ещё пуст: первая отправка ещё впереди.
                self._fetch_book.succeeded(project.folder)
                await self._update_state(project, lambda s: with_success(s, at=_now()))
                return
            await self._record_failure(project, exc, fetch=True)
            raise
        # Связь есть: растущая после сбоев пауза фоновой выборки больше не нужна.
        self._fetch_book.succeeded(project.folder)
        await self._update_state(project, lambda s: replace(with_success(s, at=_now()), remote_empty=False))

    async def _apply(
        self,
        project: Project,
        operation_id: str,
        sync_id: str,
        resolve: ResolveRequest | None,
        theirs_ref: str | None = None,
    ) -> ApplyOutcome:
        for _ in range(MAX_APPLY_ATTEMPTS):
            await self._wait_for_builds(project, operation_id)
            self._phase(operation_id, OperationPhase.merge, cancellable=False)
            async with self._locks.for_folder(project.folder):
                if self._dispatcher.has_active_for_folder(project.folder):
                    continue
                try:
                    return await asyncio.to_thread(self._apply_locked, project, sync_id, resolve, theirs_ref)
                except HeadMovedError:
                    continue
        raise git_error(GitErrorCode.sync_busy)

    def _apply_locked(
        self, project: Project, sync_id: str, resolve: ResolveRequest | None, theirs_ref: str | None
    ) -> ApplyOutcome:
        if theirs_ref is not None:
            return self._applier.apply(project, self._local_state(project), sync_id, theirs_ref)
        state = self._load_state(project)
        if resolve is None:
            return self._applier.apply(project, state, sync_id)
        return self._applier.apply_resolved(project, state, sync_id, resolve)

    async def _wait_for_builds(self, project: Project, operation_id: str) -> None:
        """Сборка читает файлы проекта, а применение их переписывает: ждём, пока она закончится."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + BUILD_WAIT_S
        while self._dispatcher.has_active_for_folder(project.folder):
            self._phase(operation_id, OperationPhase.queued, cancellable=True)
            if loop.time() >= deadline:
                raise git_error(GitErrorCode.sync_busy_build)
            await asyncio.sleep(BUILD_POLL_S)

    async def _push(self, project: Project, target: RemoteTarget, operation_id: str) -> int:
        """Отправляет закреплённый коммит. Возвращает число отправленных коммитов (0: слать нечего)."""
        state = await asyncio.to_thread(self._load_state, project)
        prepared = await asyncio.to_thread(self._prepare_push, project, state)
        if prepared is None:
            return 0
        head, ahead, first = prepared
        self._phase(operation_id, OperationPhase.push, cancellable=True)
        try:
            await self._transport.push(
                self._remotes.git_dir(project),
                target,
                local_sha=head,
                remote_branch=state.remote_branch,
                timeout_s=self._policy.first_push_timeout_s if first else None,
                on_progress=lambda percent, _line: self._operations.update(operation_id, percent=percent),
            )
        except GitSyncError as exc:
            if exc.code is not GitErrorCode.remote_moved:
                await self._record_failure(project, exc, fetch=False)
            raise
        # Коммиты уже на сервере: отмена здесь выдала бы «отменено» при том, что отправка прошла, и не записала бы
        # итог в last_sync. Дальше идёт только запись состояния.
        self._phase(operation_id, OperationPhase.push, cancellable=False)
        return ahead

    def _prepare_push(self, project: Project, state: SyncState) -> tuple[str, int, bool] | None:
        """(коммит, сколько коммитов уйдёт, первая ли это отправка) или None, если слать нечего."""
        folder = project.folder
        head = self._reader.rev_parse(folder, f"{HEADS_PREFIX}{state.local_branch}")
        if head is None:
            raise git_error(GitErrorCode.branch_missing)
        tracking = self._reader.rev_parse(folder, f"{TRACKING_PREFIX}{state.remote_branch}")
        if tracking is not None:
            if head == tracking or self._reader.is_ancestor(folder, head, tracking):
                return None
            if not self._reader.is_ancestor(folder, tracking, head):
                # Выборка фоном принесла новые коммиты после нашего применения: сервер всё равно отказал бы.
                raise git_error(GitErrorCode.remote_moved)
        self._check_before_push(folder, head, tracking)
        ahead = self._reader.count_commits(folder, f"{tracking}..{head}" if tracking else head)
        return head, ahead, tracking is None

    def _check_before_push(self, folder: Path, head: str, tracking: str | None) -> None:
        """Отказ до долгой загрузки: маркеры конфликта в файлах и блобы, которые сервер не примет."""
        marked = self._files_with_markers(folder, head, tracking)
        if marked:
            raise git_error(GitErrorCode.sync_incomplete, paths=marked[:_MAX_LISTED_PATHS])
        large = self._reader.large_blobs(
            folder, head, min_bytes=self._policy.large_file_bytes, exclude_reachable_from=tracking
        )
        if large:
            raise git_error(GitErrorCode.large_file, paths=[blob.path for blob in large[:_MAX_LISTED_PATHS]])

    def _files_with_markers(self, folder: Path, head: str, tracking: str | None) -> list[str]:
        if tracking is not None:
            paths = [path for status, path in self._reader.changed_paths(folder, tracking, head) if status != "D"]
        else:
            paths = [
                e.path
                for e in self._reader.tree_entries(folder, head)
                if e.kind == "blob" and (e.size or 0) <= _MARKER_SCAN_LIMIT
            ]
        found: list[str] = []
        for start in range(0, len(paths), _MARKER_BATCH):
            chunk = paths[start : start + _MARKER_BATCH]
            for path, content in self._reader.read_files(folder, head, chunk).items():
                if (
                    content
                    and len(content) <= _MARKER_SCAN_LIMIT
                    and has_hse_markers(content)
                    and not is_binary(path, content)
                ):
                    found.append(path)
        return sorted(found)

    async def _finish(
        self, project: Project, sync_id: str, totals: _Totals, outcome: SyncOutcome, applied: ApplyOutcome
    ) -> SyncResult:
        at = _now()

        def change(state: SyncState) -> SyncState:
            return replace(
                state,
                health=SyncHealth.ok,
                last_error=None,
                remote_empty=state.remote_empty and totals.pushed == 0,
                last_sync=LastSync(sync_id, at, outcome, totals.pulled, totals.pushed),
            )

        await self._update_state(project, change)
        logger.info(
            "git sync finished",
            project_id=str(project.id),
            outcome=outcome.value,
            pulled=totals.pulled,
            pushed=totals.pushed,
        )
        return SyncResult(
            outcome=outcome,
            pulled_commits=totals.pulled,
            pushed_commits=totals.pushed,
            merge_commit=totals.merge_commit,
            files_changed=totals.files_changed,
            auto=tuple(totals.auto[:200]),
            conflicts=applied.conflicts,
            warnings=tuple(totals.warnings),
        )
