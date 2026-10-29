"""Тик фоновой выборки: обходит проекты с подключённым репозиторием и опрашивает те, кому пора.

Без подключённых репозиториев тик ничего не делает: реестр пуст, git и сеть не запускаются. Пора ли проекту,
решает расписание (core/git_sync/fetch_schedule): общий период из настроек или собственный проекта, разброс на
проект, удвоение задержки после сбоя связи. После отказа в доступе опрос стоит, пока человек не нажмёт кнопку
или не заменит токен. Ноль в настройках выключает выборку для всех.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.entities import StoreRemoteConfig, SyncState
from hse_doc_studio.core.git_sync.fetch_schedule import (
    FetchBook,
    credential_replaced,
    halts_auto_fetch,
    next_attempt_at,
)
from hse_doc_studio.core.git_sync.protocols import (
    IGitCredentialRepository,
    IGitOperationRegistry,
    IGitRemoteRegistry,
    IGitStoreRemotes,
    IGitSyncStateRepository,
)
from hse_doc_studio.core.repositories import IProjectRepository, ISettingsRepository
from hse_doc_studio.use_cases.git_sync.fetch_remote import Clock, FetchGitRemoteUC, FetchResult, utc_now
from hse_doc_studio.use_cases.git_sync.status import default_state, fetch_interval

logger = structlog.get_logger()


@dataclass(frozen=True)
class FetchTickResult:
    """Итог одного тика. `registered == 0` говорит планировщику, что можно долго спать."""

    registered: int = 0
    fetched: int = 0
    failed: int = 0
    skipped: int = 0


class FetchAllGitRemotesUC:
    def __init__(
        self,
        *,
        registry: IGitRemoteRegistry,
        project_repo: IProjectRepository,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        operations: IGitOperationRegistry,
        credentials: IGitCredentialRepository,
        settings_repo: ISettingsRepository,
        fetch: FetchGitRemoteUC,
        book: FetchBook,
        concurrency: int,
        clock: Clock = utc_now,
    ) -> None:
        self._registry = registry
        self._projects = project_repo
        self._remotes = store_remotes
        self._states = state_repo
        self._operations = operations
        self._credentials = credentials
        self._settings = settings_repo
        self._fetch = fetch
        self._book = book
        self._concurrency = max(1, concurrency)
        self._clock = clock

    async def run_once(self) -> FetchTickResult:
        folders = await self._registry.list()
        if not folders:
            return FetchTickResult()
        stored = await self._settings.get()
        gate = asyncio.Semaphore(self._concurrency)
        outcomes = await asyncio.gather(*(self._one(folder, stored, gate) for folder in folders))
        return FetchTickResult(
            registered=len(folders),
            fetched=outcomes.count(FetchResult.fetched),
            failed=outcomes.count(FetchResult.failed),
            skipped=sum(1 for item in outcomes if item in (None, FetchResult.skipped, FetchResult.debounced)),
        )

    async def _one(self, folder: Path, stored: dict[str, Any], gate: asyncio.Semaphore) -> FetchResult | None:
        """None: проект не опрашивали (не подошёл срок, выключено, остановлено до действия человека)."""
        try:
            project = await asyncio.to_thread(self._due_project, folder, stored)
            if project is None:
                return None
            async with gate:
                return (await self._fetch.fetch(project, manual=False)).result
        except Exception:  # noqa: BLE001 — один сломанный проект не должен остановить опрос остальных
            logger.warning("git background fetch failed", folder=str(folder), exc_info=True)
            return FetchResult.failed

    def _due_project(self, folder: Path, stored: dict[str, Any]) -> Project | None:
        project = self._projects.get(folder)
        if project is None or self._book.held(folder, self._clock()):
            return None
        loaded = self._load_state(project, folder)
        if loaded is None:
            return None
        state, config = loaded
        if not self._is_due(folder, state, stored):
            return None
        # Пора опрашивать: теперь подключение читается в любом случае (запуск git оправдан), и проект,
        # у которого его больше нет, выпадает из реестра.
        config = config or self._remotes.read(project)
        if config is None:
            self._registry.remove(folder)
            return None
        if halts_auto_fetch(state) and not self._credential_replaced(state, config.credential_id):
            return None
        return project

    def _is_due(self, folder: Path, state: SyncState, stored: dict[str, Any]) -> bool:
        enabled, interval = fetch_interval(state, stored)
        if not enabled or self._operations.is_busy(folder):
            return False
        due = next_attempt_at(state.last_fetch_at, interval, self._book.failures(folder), str(folder.resolve()))
        return due is None or due <= self._clock()

    def _load_state(self, project: Project, folder: Path) -> tuple[SyncState, StoreRemoteConfig | None] | None:
        """Состояние проекта и, если пришлось его читать, подключение; None: подключения больше нет."""
        state = self._states.get(folder)
        if state is not None:
            return state, None
        # Состояния ещё нет: подключение известно только из config хранилища, и ради него запускается git.
        config = self._remotes.read(project)
        if config is None:
            self._registry.remove(folder)
            return None
        return default_state(config, None), config

    def _credential_replaced(self, state: SyncState, config_credential: UUID | None) -> bool:
        credential_id = state.credential_id or config_credential
        credential = self._credentials.get(credential_id) if credential_id else None
        return credential_replaced(state, credential)
