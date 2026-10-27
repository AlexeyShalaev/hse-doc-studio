"""Запуск синхронизации: быстрые проверки, операция в реестре и фоновая задача.

Всё, что можно сказать человеку сразу (нет профиля, чужая ветка, чужое хранилище), приходит ответом на запрос.
Дальше работа идёт в фоне, а ход и итог читаются через GET /git/operations/{id} и статус проекта: запрос на
синхронизацию не должен висеть, пока сервер качает историю.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import OperationKind, SyncState
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IGitCredentialRepository,
    IGitOperationRegistry,
    IGitRepoReader,
    IGitStoreGuard,
    IGitStoreRemotes,
    IGitSyncStateRepository,
    ILocalAuthorProfile,
    IRemoteProjectCheck,
)
from hse_doc_studio.core.git_sync.remote_project import PROJECT_FILE, require_mergeable_project
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.template_update.protocols import IUpdateJournalRepository
from hse_doc_studio.use_cases.git_sync.status import default_state
from hse_doc_studio.use_cases.git_sync.sync_apply import HEADS_PREFIX, TRACKING_PREFIX
from hse_doc_studio.use_cases.git_sync.sync_project import SyncProjectUC
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

_OPEN_FILE_MERGE = (
    "Идёт слияние с файлом проекта и в нём остались конфликты. Решите их или откажитесь от слияния",
    "A merge with a project file is open and has conflicts. Resolve them or discard the merge",
)


@dataclass
class StartSyncInput:
    project_id: UUID


@dataclass
class StartSyncOutput:
    operation_id: str


class StartSyncUC:
    def __init__(
        self,
        *,
        get_project: GetProjectUC,
        sync: SyncProjectUC,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        reader: IGitRepoReader,
        guard: IGitStoreGuard,
        credentials: IGitCredentialRepository,
        profile: ILocalAuthorProfile,
        operations: IGitOperationRegistry,
        journals: IUpdateJournalRepository,
        policy: GitSyncPolicy,
        project_check: IRemoteProjectCheck,
    ) -> None:
        self._get_project = get_project
        self._sync = sync
        self._remotes = store_remotes
        self._states = state_repo
        self._reader = reader
        self._guard = guard
        self._credentials = credentials
        self._profile = profile
        self._operations = operations
        self._journals = journals
        self._policy = policy
        self._project_check = project_check

    async def execute(self, inp: StartSyncInput) -> StartSyncOutput:
        project = (await self._get_project.execute(GetProjectInput(project_id=inp.project_id))).project
        await asyncio.to_thread(self.preflight, project)
        operation = self._operations.begin(OperationKind.sync, project_id=project.id, folder=project.folder)
        task = asyncio.create_task(self._sync.run(project, operation.id), name=f"git-sync-{operation.id}")
        self._operations.attach_task(operation.id, task)
        return StartSyncOutput(operation_id=operation.id)

    def preflight(self, project: Project) -> None:
        """Быстрые проверки перед любой операцией синхронизации; общие с применением решений по конфликтам."""
        self._policy.require_enabled()
        config = self._remotes.read(project)
        if config is None:
            raise NotFoundError(localized_error("Удалённый репозиторий не подключён", "No remote is connected"))
        if self._profile.get() is None:
            raise git_error(GitErrorCode.profile_required)
        self._guard.ensure_trusted(project.folder)
        state = self._states.get(project.folder) or default_state(config, None)
        credential_id = state.credential_id or config.credential_id
        if credential_id is not None and self._credentials.get(credential_id) is None:
            raise git_error(GitErrorCode.credentials_missing)
        if state.pending is not None and state.pending.theirs_ref is not None:
            # Открытое слияние с файлом: синхронизация с сервером затёрла бы сессию, а с ней решения человека.
            raise GitSyncError(GitErrorCode.sync_incomplete, localized_error(*_OPEN_FILE_MERGE))
        self._check_branches(project, state)
        if self._journals.get(project.folder) is not None:
            raise git_error(GitErrorCode.sync_incomplete)

    def _check_branches(self, project: Project, state: SyncState) -> None:
        folder = project.folder
        if self._reader.current_branch(folder) != state.local_branch:
            raise git_error(GitErrorCode.off_branch)
        if self._reader.rev_parse(folder, f"{HEADS_PREFIX}{state.local_branch}") is None:
            raise git_error(GitErrorCode.branch_missing)
        tracking = self._reader.rev_parse(folder, f"{TRACKING_PREFIX}{state.remote_branch}")
        if tracking is not None:
            # Известная вершина чужой ветки уже говорит, откроет ли эта Студия такой проект.
            raw = self._reader.read_files(folder, tracking, [PROJECT_FILE]).get(PROJECT_FILE)
            require_mergeable_project(raw, project.id, self._project_check)
