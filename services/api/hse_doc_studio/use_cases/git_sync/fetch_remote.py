"""Выборка изменений из удалённого репозитория: кнопкой, при открытии проекта и по расписанию.

Выборка только скачивает ветку в `refs/remotes/origin/<ветка>` и записывает в hse-sync.json, чем всё кончилось.
Папка проекта при этом не блокируется: правки и сборки идут как обычно, а дерево проекта не меняется вовсе.
Отказ сети или доступа не исключение для вызывающего, а состояние (health и last_error в статусе): так интерфейс
показывает «нет связи» или «нет доступа» в одном месте и не сыплет ошибками при каждом возврате в окно.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.entities import (
    GitOperationError,
    RemoteTarget,
    StoreRemoteConfig,
    SyncHealth,
    SyncState,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.fetch_schedule import MAX_BACKOFF_S, FetchBook
from hse_doc_studio.core.git_sync.policy import FETCH_DEBOUNCE_S, GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IGitOperationRegistry,
    IGitRepoReader,
    IGitStoreGuard,
    IGitStoreRemotes,
    IGitSyncStateRepository,
    IGitTransport,
)
from hse_doc_studio.core.git_sync.remote_project import PROJECT_FILE, parse_remote_project, schema_blocks_merge
from hse_doc_studio.core.git_sync.url import parse_remote_url
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.use_cases.git_sync.health import with_failure, with_success
from hse_doc_studio.use_cases.git_sync.status import (
    TRACKING_PREFIX,
    GitStatusBuilder,
    GitStatusView,
    default_state,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class FetchResult(StrEnum):
    fetched = "fetched"
    failed = "failed"
    debounced = "debounced"
    skipped = "skipped"


@dataclass(frozen=True)
class FetchOutcome:
    result: FetchResult
    error: GitOperationError | None = None


@dataclass
class FetchGitRemoteInput:
    project_id: UUID


class FetchGitRemoteUC:
    def __init__(
        self,
        *,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        reader: IGitRepoReader,
        transport: IGitTransport,
        guard: IGitStoreGuard,
        operations: IGitOperationRegistry,
        status_builder: GitStatusBuilder,
        policy: GitSyncPolicy,
        book: FetchBook,
        clock: Clock = utc_now,
    ) -> None:
        self._get_project = GetProjectUC(project_repo, project_index_repo)
        self._remotes = store_remotes
        self._states = state_repo
        self._reader = reader
        self._transport = transport
        self._guard = guard
        self._operations = operations
        self._status = status_builder
        self._policy = policy
        self._book = book
        self._clock = clock

    async def execute(self, inp: FetchGitRemoteInput) -> GitStatusView:
        """По просьбе интерфейса: не чаще раза в FETCH_DEBOUNCE_S, итог всегда в статусе."""
        project = (await self._get_project.execute(GetProjectInput(project_id=inp.project_id))).project
        await self.fetch(project, manual=True)
        return await self._status.view(project)

    async def fetch(self, project: Project, *, manual: bool) -> FetchOutcome:
        """Одна выборка. `manual=False` это расписание: занятую папку и недоверенное хранилище оно молча пропускает.

        Просьбы интерфейса присоединяются к идущей выборке и получают её итог: при недоступном сервере каждая
        просьба иначе запускала бы собственную попытку на весь срок и ставилась бы в очередь за предыдущими.
        """
        folder = project.folder
        if not self._policy.enabled:
            return FetchOutcome(FetchResult.skipped)
        config = await asyncio.to_thread(self._remotes.read, project)
        if config is None:
            return FetchOutcome(FetchResult.skipped)
        lock = self._book.lock(folder)
        if self._is_busy(project, manual=manual) or (lock.locked() and not manual):
            return FetchOutcome(FetchResult.skipped)
        running = self._book.running(folder)
        if running is not None:
            # Отмена просьбы (клиент ушёл) не должна обрывать выборку, которую ждут другие: ждём через shield.
            return await asyncio.shield(running) if manual else FetchOutcome(FetchResult.skipped)
        task = asyncio.ensure_future(self._fetch_exclusive(project, manual=manual))
        self._book.track(folder, task)
        return await asyncio.shield(task)

    async def _fetch_exclusive(self, project: Project, *, manual: bool) -> FetchOutcome:
        async with self._book.lock(project.folder):
            # Пока ждали замок, могла начаться синхронизация, а проект отключиться, переехать или сменить адрес.
            if self._is_busy(project, manual=manual):
                return FetchOutcome(FetchResult.skipped)
            config = await asyncio.to_thread(self._remotes.read, project)
            if config is None:
                return FetchOutcome(FetchResult.skipped)
            return await self._fetch_locked(project, config, manual=manual)

    def _is_busy(self, project: Project, *, manual: bool) -> bool:
        """Идёт операция над папкой: расписание её пропускает, кнопка получает sync_busy."""
        if not self._operations.is_busy(project.folder):
            return False
        if manual:
            current = self._operations.current_for(project.id)
            raise git_error(GitErrorCode.sync_busy, operation_id=current.id if current else None)
        return True

    async def _fetch_locked(self, project: Project, config: StoreRemoteConfig, *, manual: bool) -> FetchOutcome:
        folder = project.folder
        try:
            await asyncio.to_thread(self._guard.ensure_trusted, folder)
        except GitSyncError:
            if manual:
                raise
            logger.warning("git fetch skipped: store is not trusted", project_id=str(project.id))
            # Без паузы расписание повторяло бы отказ и предупреждение в журнале при каждом тике.
            self._book.hold(folder, self._clock() + timedelta(seconds=MAX_BACKOFF_S))
            return FetchOutcome(FetchResult.skipped)
        state = await asyncio.to_thread(self._load_state, project, config)
        now = self._clock()
        if manual and self._debounced(state, now):
            return FetchOutcome(FetchResult.debounced)
        target = RemoteTarget(
            parse_remote_url(
                config.url,
                allow_http=self._policy.allow_insecure_http,
                allow_local=self._policy.allow_local_remotes,
            ),
            state.credential_id or config.credential_id,
            insecure_http=state.insecure_http,
            project_id=project.id,
        )
        tracking = f"{TRACKING_PREFIX}{state.remote_branch}"
        before = await asyncio.to_thread(self._reader.rev_parse, folder, tracking)
        error: GitSyncError | None = None
        try:
            await self._transport.fetch(self._remotes.git_dir(project), target, branch=state.remote_branch)
        except GitSyncError as exc:
            error = exc
        if error is not None and not _remote_still_empty(state, error):
            self._book.failed(folder)
            await asyncio.to_thread(self._record_failure, project, config, error)
            logger.info("git fetch failed", project_id=str(project.id), code=error.code.value)
            return FetchOutcome(FetchResult.failed, GitOperationError(error.code, error.detail))
        self._book.succeeded(folder)
        await asyncio.to_thread(self._record_success, project, config, before)
        return FetchOutcome(FetchResult.fetched)

    def _load_state(self, project: Project, config: StoreRemoteConfig) -> SyncState:
        return self._states.get(project.folder) or default_state(config, None)

    @staticmethod
    def _debounced(state: SyncState, now: datetime) -> bool:
        """Недавняя удачная выборка; после сбоя окно не действует: повтор по просьбе человека должен дойти до сети."""
        ok_at = state.last_fetch_ok_at
        if state.health is not SyncHealth.ok or ok_at is None:
            return False
        return timedelta(0) <= now - ok_at < timedelta(seconds=FETCH_DEBOUNCE_S)

    def _record_failure(self, project: Project, config: StoreRemoteConfig, error: GitSyncError) -> None:
        now = self._clock()
        self._save(
            project,
            config,
            lambda state: with_failure(state, error, at=now, fetch=True),
        )

    def _record_success(self, project: Project, config: StoreRemoteConfig, before: str | None) -> None:
        now = self._clock()
        folder = project.folder

        def changed(state: SyncState) -> SyncState:
            tracking = f"{TRACKING_PREFIX}{state.remote_branch}"
            after = self._reader.rev_parse(folder, tracking)
            newer, required = self._remote_schema(folder, tracking, after, before, state)
            return replace(
                with_success(state, at=now),
                # Ветка на сервере появилась: первая отправка уже не первая, сравнение идёт с ней.
                remote_empty=state.remote_empty and after is None,
                remote_schema_newer=newer,
                remote_required_studio=required,
            )

        self._save(project, config, changed)

    def _remote_schema(
        self, folder: Path, tracking: str, after: str | None, before: str | None, state: SyncState
    ) -> tuple[bool, str | None]:
        """Записан ли конец удалённой ветки более новой Студией; читается только при новом конце ветки."""
        if after is None:
            return False, None
        if after == before and not state.remote_schema_newer:
            return False, None
        raw = self._reader.read_files(folder, tracking, [PROJECT_FILE]).get(PROJECT_FILE)
        remote = parse_remote_project(raw) if raw is not None else None
        if remote is None or not schema_blocks_merge(remote.schema):
            return False, None
        return True, remote.schema.written_by or None

    def _save(self, project: Project, config: StoreRemoteConfig, change: Callable[[SyncState], SyncState]) -> None:
        """Состояние перечитывается перед записью: за время сети его могли изменить настройки или синхронизация."""
        if self._operations.is_busy(project.folder):
            return
        self._states.save(project.folder, change(self._load_state(project, config)))


def _remote_still_empty(state: SyncState, error: GitSyncError) -> bool:
    """Подключались к пустому репозиторию, и ветки на нём до сих пор нет: это не сбой."""
    return state.remote_empty and error.code is GitErrorCode.branch_missing
