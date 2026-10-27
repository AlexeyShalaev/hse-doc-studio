"""Подключение проекта к удалённому репозиторию и отключение от него.

Подключение проверяет всё до записи: профиль автора, доверие к хранилищу, адрес, доступ и содержимое
репозитория. Если на сервере уже есть проект, его ветка скачивается в хранилище, и по ней видно, тот ли это
проект и есть ли у историй общее начало. Только после этого адрес и привязка к доступу попадают в config
хранилища, а состояние синхронизации в hse-sync.json. Любой отказ оставляет проект как был.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.entities import (
    GitOperationError,
    OperationKind,
    OperationPhase,
    OperationStatus,
    RemoteTarget,
    StoreRemoteConfig,
    SyncState,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.fetch_schedule import FetchBook
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IGitCredentialRepository,
    IGitCredentialUsage,
    IGitOperationRegistry,
    IGitRemoteRegistry,
    IGitRepoReader,
    IGitStoreGuard,
    IGitStoreRemotes,
    IGitSyncStateRepository,
    IGitTransport,
    ILocalAuthorProfile,
    IRemoteProjectCheck,
)
from hse_doc_studio.core.git_sync.remote_project import PROJECT_FILE, require_mergeable_project
from hse_doc_studio.core.git_sync.url import RemoteUrl, parse_remote_url
from hse_doc_studio.use_cases.git_sync.probe_remote import choose_remote_branch, raise_probe_error, valid_branch
from hse_doc_studio.use_cases.git_sync.status import (
    HEADS_PREFIX,
    TRACKING_PREFIX,
    GitStatusBuilder,
    GitStatusView,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.vcs.ensure_vcs import EnsureVcsInput, EnsureVcsUC

logger = structlog.get_logger()

ADOPT_MERGE_REMOTE = "merge_remote"


@dataclass
class ConnectRemoteInput:
    project_id: UUID
    url: str
    credential_id: UUID | None = None
    branch: str | None = None
    remote_branch: str | None = None
    adopt: str | None = None
    insecure_http: bool = False


class ConnectRemoteUC:
    def __init__(
        self,
        *,
        get_project: GetProjectUC,
        ensure_vcs: EnsureVcsUC,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        reader: IGitRepoReader,
        transport: IGitTransport,
        guard: IGitStoreGuard,
        credentials: IGitCredentialRepository,
        profile: ILocalAuthorProfile,
        operations: IGitOperationRegistry,
        registry: IGitRemoteRegistry,
        status_builder: GitStatusBuilder,
        policy: GitSyncPolicy,
        project_check: IRemoteProjectCheck,
        fetch_book: FetchBook,
    ) -> None:
        self._get_project = get_project
        self._ensure_vcs = ensure_vcs
        self._remotes = store_remotes
        self._states = state_repo
        self._reader = reader
        self._transport = transport
        self._guard = guard
        self._credentials = credentials
        self._profile = profile
        self._operations = operations
        self._registry = registry
        self._status = status_builder
        self._policy = policy
        self._project_check = project_check
        self._fetch_book = fetch_book

    async def execute(self, inp: ConnectRemoteInput) -> GitStatusView:
        project = (await self._get_project.execute(GetProjectInput(project_id=inp.project_id))).project
        url = self._checked_input(inp)
        await self._prepare_store(project)
        if await asyncio.to_thread(self._remotes.read, project) is not None:
            raise git_error(GitErrorCode.remote_exists)
        local_branch = await asyncio.to_thread(self._local_branch, project, inp.branch)
        operation = self._operations.begin(OperationKind.connect, project_id=project.id, folder=project.folder)
        try:
            self._operations.update(operation.id, phase=OperationPhase.fetch)
            await self._connect(project, url, local_branch, inp, operation.id)
        except asyncio.CancelledError:
            self._operations.finish(operation.id, status=OperationStatus.cancelled)
            raise
        except GitSyncError as exc:
            self._operations.finish(
                operation.id, status=OperationStatus.failed, error=GitOperationError(exc.code, exc.detail)
            )
            raise
        except Exception:
            self._operations.finish(
                operation.id,
                status=OperationStatus.failed,
                error=GitOperationError(GitErrorCode.git_error, ""),
            )
            raise
        self._operations.finish(operation.id)
        return await asyncio.to_thread(self._status.build, project)

    def _checked_input(self, inp: ConnectRemoteInput) -> RemoteUrl:
        self._policy.require_enabled()
        if inp.adopt not in (None, ADOPT_MERGE_REMOTE):
            raise ValueError("adopt must be null or 'merge_remote'")
        if self._profile.get() is None:
            raise git_error(GitErrorCode.profile_required)
        url = parse_remote_url(
            inp.url, allow_http=self._policy.allow_insecure_http, allow_local=self._policy.allow_local_remotes
        )
        if inp.credential_id is not None and self._credentials.get(inp.credential_id) is None:
            raise git_error(GitErrorCode.credentials_missing)
        return url

    async def _prepare_store(self, project: Project) -> None:
        """Чужое хранилище проверяется до любой команды над ним, затем при необходимости создаётся своё."""
        await asyncio.to_thread(self._guard.ensure_trusted, project.folder)
        ensured = await self._ensure_vcs.execute(EnsureVcsInput(project_id=project.id))
        if not ensured.initialized:
            raise ValueError("The project folder is not accessible")

    def _local_branch(self, project: Project, requested: str | None) -> str:
        if requested:
            branch = valid_branch(requested)
        else:
            current = self._reader.current_branch(project.folder)
            if current is None:
                raise git_error(GitErrorCode.off_branch)
            branch = current
        if self._reader.rev_parse(project.folder, f"{HEADS_PREFIX}{branch}") is None:
            raise git_error(GitErrorCode.branch_missing)
        return branch

    async def _connect(
        self, project: Project, url: RemoteUrl, local_branch: str, inp: ConnectRemoteInput, operation_id: str
    ) -> None:
        target = RemoteTarget(url, inp.credential_id, insecure_http=inp.insecure_http)
        probe = await self._transport.probe(target)
        raise_probe_error(probe)
        remote_branch = valid_branch(choose_remote_branch(inp.remote_branch, probe))
        adopted = False
        if not probe.empty:
            if remote_branch not in probe.branches:
                raise git_error(GitErrorCode.branch_missing)
            adopted = await self._check_remote_project(project, target, local_branch, remote_branch, inp, operation_id)
        now = datetime.now(UTC)
        state = SyncState(
            local_branch=local_branch,
            remote_branch=remote_branch,
            credential_id=inp.credential_id,
            insecure_http=inp.insecure_http,
            last_fetch_at=now,
            last_fetch_ok_at=now,
            remote_empty=probe.empty,
            adopted_unrelated=adopted,
        )
        await asyncio.to_thread(self._persist, project, url, state)

    async def _check_remote_project(
        self,
        project: Project,
        target: RemoteTarget,
        local_branch: str,
        remote_branch: str,
        inp: ConnectRemoteInput,
        operation_id: str,
    ) -> bool:
        """Скачивает ветку и проверяет, что на сервере тот же проект. True: принято слияние без общей истории."""
        git_dir = self._remotes.git_dir(project)
        try:
            # Фоновая выборка того же проекта не должна двигать отслеживаемую ветку, пока её проверяют.
            async with self._fetch_book.lock(project.folder):
                await self._transport.fetch(
                    git_dir,
                    target,
                    branch=remote_branch,
                    on_progress=lambda percent, _line: self._operations.update(operation_id, percent=percent),
                )
                adopted = await asyncio.to_thread(self._verify_remote, project, local_branch, remote_branch, inp)
        except BaseException:
            await asyncio.to_thread(self._remotes.drop_tracking_refs, project)
            raise
        self._fetch_book.succeeded(project.folder)
        return adopted

    def _verify_remote(self, project: Project, local_branch: str, remote_branch: str, inp: ConnectRemoteInput) -> bool:
        folder = project.folder
        tracking = f"{TRACKING_PREFIX}{remote_branch}"
        raw = self._reader.read_files(folder, tracking, [PROJECT_FILE]).get(PROJECT_FILE)
        require_mergeable_project(raw, project.id, self._project_check)
        if self._reader.merge_base(folder, f"{HEADS_PREFIX}{local_branch}", tracking) is not None:
            return False
        if inp.adopt != ADOPT_MERGE_REMOTE:
            raise git_error(GitErrorCode.unrelated_histories, can_adopt=True)
        return True

    def _persist(self, project: Project, url: RemoteUrl, state: SyncState) -> None:
        config = StoreRemoteConfig(
            url=url.display_url,
            credential_id=state.credential_id,
            local_branch=state.local_branch,
            remote_branch=state.remote_branch,
        )
        self._remotes.write(project, config)
        self._states.save(project.folder, state)
        self._registry.add(project.folder)
        logger.info(
            "git remote connected",
            project_id=str(project.id),
            host=url.host,
            kind=url.kind.value,
            remote_branch=state.remote_branch,
        )


@dataclass
class DisconnectRemoteInput:
    project_id: UUID
    forget_credential: bool = False


class DisconnectRemoteUC:
    """Отключает проект от удалённого репозитория; сам репозиторий и сохранённые доступы остаются."""

    def __init__(
        self,
        *,
        get_project: GetProjectUC,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        operations: IGitOperationRegistry,
        registry: IGitRemoteRegistry,
        credentials: IGitCredentialRepository,
        credential_usage: IGitCredentialUsage,
        fetch_book: FetchBook,
    ) -> None:
        self._get_project = get_project
        self._remotes = store_remotes
        self._states = state_repo
        self._operations = operations
        self._registry = registry
        self._credentials = credentials
        self._usage = credential_usage
        self._fetch_book = fetch_book

    async def execute(self, inp: DisconnectRemoteInput) -> None:
        project = (await self._get_project.execute(GetProjectInput(project_id=inp.project_id))).project
        if self._operations.is_busy(project.folder):
            current = self._operations.current_for(project.id)
            raise git_error(GitErrorCode.sync_busy, operation_id=current.id if current else None)
        # Выборка, которая ещё идёт, вернула бы отслеживаемую ветку и состояние, которые отключение только что убрало.
        async with self._fetch_book.lock(project.folder):
            await asyncio.to_thread(self._disconnect, project, inp.forget_credential)
        self._fetch_book.forget(project.folder)

    def _disconnect(self, project: Project, forget_credential: bool) -> None:
        config = self._remotes.read(project)
        credential_id = None
        if config is not None:
            state = self._states.get(project.folder)
            credential_id = (state.credential_id if state else None) or config.credential_id
            self._remotes.clear(project)
        self._states.clear(project.folder)
        self._registry.remove(project.folder)
        if forget_credential and credential_id is not None and not self._used_elsewhere(credential_id, project.id):
            self._credentials.delete(credential_id)
        logger.info("git remote disconnected", project_id=str(project.id), forgot_credential=forget_credential)

    def _used_elsewhere(self, credential_id: UUID, project_id: UUID) -> bool:
        return any(u.project_id != project_id for u in self._usage.by_credential().get(credential_id, ()))
