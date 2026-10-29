"""Состояние синхронизации проекта: то, что видит человек в кнопке «Синхронизировать» и в статус-баре.

Статус считается по ссылкам и файлам хранилища, без сети и без `git status`: его опрашивают раз в секунду, пока
идёт операция, и раз в полминуты в покое. Дорогое сравнение веток запоминается по коммитам на их концах.
Проект без удалённого репозитория ничего не стоит: файл config читается как текст, git не запускается.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.entities import (
    CommitBrief,
    GitCredentialKind,
    GitOperation,
    LastError,
    LastSync,
    PendingSession,
    StoreRemoteConfig,
    SyncBlockReason,
    SyncHealth,
    SyncRelation,
    SyncState,
    SyncUiState,
)
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.policy import (
    DEFAULT_FETCH_INTERVAL_S,
    DEFAULT_REMOTE_BRANCH,
    MIN_FETCH_INTERVAL_S,
    GitSyncPolicy,
)
from hse_doc_studio.core.git_sync.protocols import (
    IGitCredentialRepository,
    IGitOperationRegistry,
    IGitRepoReader,
    IGitStoreGuard,
    IGitStoreRemotes,
    IGitSyncStateRepository,
    ILocalAuthorProfile,
    ISharedFolderDetector,
)
from hse_doc_studio.core.git_sync.providers import ProviderInfo, detect_provider
from hse_doc_studio.core.git_sync.status import (
    RefComparison,
    RefStatusMemo,
    StatusInputs,
    derive_relation,
    derive_ui_state,
)
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl, parse_remote_url
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ISettingsRepository
from hse_doc_studio.core.vcs.errors import VcsCommandError, VcsUnavailableError
from hse_doc_studio.use_cases.git_sync.provider_resolver import ProviderResolver
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.projects.get_project_access import ProjectAccessService

logger = structlog.get_logger()

BRIEFS_LIMIT = 5
TRACKING_PREFIX = "refs/remotes/origin/"
HEADS_PREFIX = "refs/heads/"


@dataclass(frozen=True)
class CredentialRefView:
    id: UUID
    label: str
    kind: GitCredentialKind


@dataclass(frozen=True)
class RemoteInfoView:
    display_url: str
    kind: RemoteKind
    host: str | None
    provider: str
    provider_info: ProviderInfo
    web_url: str | None
    branch: str
    local_branch: str
    credential: CredentialRefView | None
    insecure_http: bool


@dataclass(frozen=True)
class BlockedView:
    reason: SyncBlockReason
    required_studio: str | None = None


@dataclass(frozen=True)
class OperationBriefView:
    id: str
    kind: str
    phase: str
    percent: float | None
    cancellable: bool
    started_at: datetime


@dataclass(frozen=True)
class AutoFetchView:
    enabled: bool
    interval_s: int
    next_fetch_at: datetime | None


@dataclass(frozen=True)
class SharedFolderView:
    provider: str
    root: str
    acknowledged: bool


@dataclass(frozen=True)
class GitStatusView:
    connected: bool
    ui_state: SyncUiState
    remote: RemoteInfoView | None
    relation: SyncRelation
    health: SyncHealth
    profile_ok: bool
    auto_fetch: AutoFetchView
    ahead: int = 0
    behind: int = 0
    behind_files: int = 0
    last_error: LastError | None = None
    blocked: BlockedView | None = None
    incoming: tuple[CommitBrief, ...] = ()
    outgoing: tuple[CommitBrief, ...] = ()
    operation: OperationBriefView | None = None
    pending: PendingSession | None = None
    last_fetch_at: datetime | None = None
    last_fetch_ok_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_sync: LastSync | None = None
    shared_folder: SharedFolderView | None = None
    bot_authored_commits: int = 0


@dataclass(frozen=True)
class _Comparison:
    relation: SyncRelation
    data: RefComparison = field(default_factory=lambda: RefComparison(0, 0, 0, (), (), 0))


def web_url_of(url: RemoteUrl) -> str | None:
    """Адрес страницы репозитория в браузере; у локальных адресов её нет."""
    if url.kind is RemoteKind.file or url.host is None or url.repo is None:
        return None
    if url.kind in (RemoteKind.https, RemoteKind.http):
        base = url.display_url.removesuffix("/").removesuffix(".git")
        return base
    if url.owner is None:
        return None
    return f"https://{url.host}/{url.owner}/{url.repo}"


def default_state(config: StoreRemoteConfig, current_branch: str | None) -> SyncState:
    """Состояние для папки, к которой пришёл config без hse-sync.json (например, скопированной с другого компьютера)."""
    return SyncState(
        local_branch=config.local_branch or current_branch or DEFAULT_REMOTE_BRANCH,
        remote_branch=config.remote_branch or DEFAULT_REMOTE_BRANCH,
        credential_id=config.credential_id,
    )


def fetch_interval(state: SyncState | None, stored_settings: dict[str, object]) -> tuple[bool, int]:
    """(включена ли выборка, период в секундах): общая настройка выше проектной, ноль выключает всем."""
    raw = stored_settings.get("git_fetch_interval_s", DEFAULT_FETCH_INTERVAL_S)
    general = raw if isinstance(raw, int) and not isinstance(raw, bool) else DEFAULT_FETCH_INTERVAL_S
    if general <= 0:
        return False, DEFAULT_FETCH_INTERVAL_S
    own = state.fetch_interval_s if state else None
    interval = max(MIN_FETCH_INTERVAL_S, own if own else general)
    return (state.auto_fetch if state else True), interval


class GitStatusBuilder:
    def __init__(
        self,
        *,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        reader: IGitRepoReader,
        operations: IGitOperationRegistry,
        profile: ILocalAuthorProfile,
        credentials: IGitCredentialRepository,
        access: ProjectAccessService,
        guard: IGitStoreGuard,
        settings_repo: ISettingsRepository,
        memo: RefStatusMemo,
        policy: GitSyncPolicy,
        shared_folders: ISharedFolderDetector | None = None,
        providers: ProviderResolver | None = None,
    ) -> None:
        self._remotes = store_remotes
        self._states = state_repo
        self._reader = reader
        self._operations = operations
        self._profile = profile
        self._credentials = credentials
        self._access = access
        self._guard = guard
        self._settings = settings_repo
        self._memo = memo
        self._policy = policy
        self._shared = shared_folders
        self._providers = providers

    async def view(self, project: Project) -> GitStatusView:
        """Настройки читаются здесь, а блокирующая часть с запусками git уходит в поток."""
        stored = await self._settings.get()
        return await asyncio.to_thread(self.build, project, stored)

    def build(self, project: Project, stored: dict[str, object]) -> GitStatusView:
        """Блокирует на запусках git: вызывающий уводит вызов в поток."""
        profile_ok = self._profile.get() is not None
        config = self._remotes.read(project)
        if config is None:
            return self._without_remote(project, stored, profile_ok)
        folder = project.folder
        current = self._current_branch(folder)
        state = self._states.get(folder) or default_state(config, current)
        blocked = self._blocked(project, state, current, profile_ok)
        comparison = self._compare(folder, state)
        operation = self._operations.current_for(project.id)
        ui_state = derive_ui_state(
            StatusInputs(
                connected=True,
                relation=comparison.relation,
                health=state.health,
                has_operation=operation is not None,
                has_pending=state.pending is not None,
                blocked=blocked.reason if blocked else None,
            )
        )
        enabled, interval = fetch_interval(state, stored)
        data = comparison.data
        return GitStatusView(
            connected=True,
            ui_state=ui_state,
            remote=self._remote_info(config, state),
            relation=comparison.relation,
            health=state.health,
            profile_ok=profile_ok,
            auto_fetch=AutoFetchView(enabled, interval, self._next_fetch(state, enabled, interval)),
            ahead=data.ahead,
            behind=data.behind,
            behind_files=data.behind_files,
            last_error=state.last_error,
            blocked=blocked,
            incoming=self._public(data.incoming),
            outgoing=self._public(data.outgoing),
            operation=_operation_brief(operation),
            pending=state.pending,
            last_fetch_at=state.last_fetch_at,
            last_fetch_ok_at=state.last_fetch_ok_at,
            last_sync_at=state.last_sync.at if state.last_sync else None,
            last_sync=state.last_sync,
            shared_folder=self._shared_folder(folder, state),
            bot_authored_commits=data.unpublished_bot_commits,
        )

    def _without_remote(self, project: Project, stored: dict[str, object], profile_ok: bool) -> GitStatusView:
        """Проект без сервера: статус пуст, кроме открытой сессии конфликтов от файла bundle."""
        enabled, interval = fetch_interval(None, stored)
        auto_fetch = AutoFetchView(enabled, interval, None)
        pending = state.pending if (state := self._states.get(project.folder)) else None
        if pending is None:
            return GitStatusView(
                connected=False,
                ui_state=SyncUiState.no_remote,
                remote=None,
                relation=SyncRelation.none,
                health=SyncHealth.ok,
                profile_ok=profile_ok,
                auto_fetch=auto_fetch,
            )
        operation = self._operations.current_for(project.id)
        return GitStatusView(
            connected=False,
            ui_state=SyncUiState.syncing if operation else SyncUiState.conflicts,
            remote=None,
            relation=SyncRelation.none,
            health=SyncHealth.ok,
            profile_ok=profile_ok,
            auto_fetch=auto_fetch,
            operation=_operation_brief(operation),
            pending=pending,
        )

    def _blocked(self, project: Project, state: SyncState, current: str | None, profile_ok: bool) -> BlockedView | None:
        if not self._guard.audit(project.folder).trusted:
            return BlockedView(SyncBlockReason.store_untrusted)
        access = self._access.evaluate(project)
        if not access.writable:
            return BlockedView(SyncBlockReason.read_only, access.required_studio)
        if state.remote_schema_newer:
            return BlockedView(SyncBlockReason.remote_schema_newer, state.remote_required_studio)
        if current != state.local_branch:
            return BlockedView(SyncBlockReason.off_branch)
        if not profile_ok:
            return BlockedView(SyncBlockReason.profile_required)
        return None

    def _current_branch(self, folder: Path) -> str | None:
        try:
            return self._reader.current_branch(folder)
        except (VcsCommandError, VcsUnavailableError) as exc:
            # Статус опрашивают постоянно: сломанное хранилище не должно превращать его в ошибку сервера.
            logger.warning("git status: store is unreadable", folder=str(folder), exc=str(exc))
            return None

    def _compare(self, folder: Path, state: SyncState) -> _Comparison:
        try:
            return self._compare_refs(folder, state)
        except (VcsCommandError, VcsUnavailableError) as exc:
            logger.warning("git status: branches cannot be compared", folder=str(folder), exc=str(exc))
            return _Comparison(SyncRelation.unfetched)

    def _compare_refs(self, folder: Path, state: SyncState) -> _Comparison:
        local = self._reader.rev_parse(folder, f"{HEADS_PREFIX}{state.local_branch}")
        tracking = self._reader.rev_parse(folder, f"{TRACKING_PREFIX}{state.remote_branch}")
        if local is None:
            return _Comparison(SyncRelation.unfetched)
        key = (str(folder), local, tracking, state.remote_empty)
        data = self._memo.get(key)
        if data is None:
            data = self._measure(folder, local, tracking, state)
            self._memo.put(key, data)
        if tracking is None:
            return _Comparison(SyncRelation.remote_empty if state.remote_empty else SyncRelation.unfetched, data)
        return _Comparison(derive_relation(ahead=data.ahead, behind=data.behind, tracking_exists=True), data)

    def _measure(self, folder: Path, local: str, tracking: str | None, state: SyncState) -> RefComparison:
        reader = self._reader
        if tracking is None:
            # Ни одной отправки ещё не было: всё, что есть, уйдёт первой отправкой (если репозиторий пуст).
            ahead = reader.count_commits(folder, local) if state.remote_empty else 0
            outgoing = tuple(reader.commit_briefs(folder, local, limit=BRIEFS_LIMIT)) if state.remote_empty else ()
            return RefComparison(ahead, 0, 0, (), outgoing, self._bot_commits(folder, local))
        ahead, behind = reader.ahead_behind(folder, local, tracking)
        incoming = tuple(reader.commit_briefs(folder, f"{local}..{tracking}", limit=BRIEFS_LIMIT)) if behind else ()
        outgoing = tuple(reader.commit_briefs(folder, f"{tracking}..{local}", limit=BRIEFS_LIMIT)) if ahead else ()
        return RefComparison(
            ahead,
            behind,
            self._behind_files(folder, local, tracking) if behind else 0,
            incoming,
            outgoing,
            self._bot_commits(folder, f"{tracking}..{local}") if ahead else 0,
        )

    def _behind_files(self, folder: Path, local: str, tracking: str) -> int:
        base = self._reader.merge_base(folder, local, tracking) or local
        return len(self._reader.changed_paths(folder, base, tracking))

    def _bot_commits(self, folder: Path, rev: str) -> int:
        counts = self._reader.author_counts(folder, rev)
        return sum(item.commits for item in counts if item.email == self._policy.bot_email)

    def _public(self, briefs: tuple[CommitBrief, ...]) -> tuple[CommitBrief, ...]:
        """Почта служебной подписи наружу не отдаётся: это не человек."""
        return tuple(
            CommitBrief(b.id, b.short_id, b.message, b.author, None, b.created_at, b.kind)
            if b.author_email == self._policy.bot_email
            else b
            for b in briefs
        )

    def _remote_info(self, config: StoreRemoteConfig, state: SyncState) -> RemoteInfoView | None:
        try:
            url = parse_remote_url(config.url, allow_http=True, allow_local=True)
        except GitSyncError:
            # Адрес в config не разбирается: хранилище уже помечено недоверенным, показывать нечего.
            return None
        credential_id = state.credential_id or config.credential_id
        credential = self._credentials.get(credential_id) if credential_id else None
        provider = self._providers.known(url.host, url.port) if self._providers else detect_provider(url.host)
        return RemoteInfoView(
            display_url=url.display_url,
            kind=url.kind,
            host=url.host,
            provider=provider.id.value,
            provider_info=provider,
            web_url=web_url_of(url),
            branch=state.remote_branch,
            local_branch=state.local_branch,
            credential=CredentialRefView(credential.id, credential.label, credential.kind) if credential else None,
            insecure_http=state.insecure_http,
        )

    @staticmethod
    def _next_fetch(state: SyncState, enabled: bool, interval: int) -> datetime | None:
        if not enabled or state.last_fetch_at is None or state.health is SyncHealth.unauthenticated:
            return None
        return state.last_fetch_at + timedelta(seconds=interval)

    def _shared_folder(self, folder: Path, state: SyncState) -> SharedFolderView | None:
        if self._shared is None:
            return None
        info = self._shared.detect(folder)
        if info is None:
            return None
        return SharedFolderView(info.provider.value, info.root, state.shared_folder_ack)


def _operation_brief(operation: GitOperation | None) -> OperationBriefView | None:
    if operation is None:
        return None
    return OperationBriefView(
        id=operation.id,
        kind=operation.kind.value,
        phase=operation.phase.value,
        percent=operation.percent,
        cancellable=operation.cancellable,
        started_at=operation.started_at,
    )


@dataclass
class GetGitStatusInput:
    project_id: UUID


class GetGitStatusUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        builder: GitStatusBuilder,
        policy: GitSyncPolicy,
    ) -> None:
        self._get_uc = GetProjectUC(project_repo, project_index_repo)
        self._builder = builder
        self._policy = policy

    async def execute(self, inp: GetGitStatusInput) -> GitStatusView:
        # Выключенная синхронизация не обещает подключения: клиент читает отказ как «не поддерживается».
        self._policy.require_enabled()
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        return await self._builder.view(project)
