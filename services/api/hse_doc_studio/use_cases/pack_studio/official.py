"""Официальные паки (docs/design/template-studio.md, 4.7, срез T22).

Кнопка «Официальные паки» создаёт или открывает рабочее пространство над официальным репозиторием паков установки
(частичный клон только папки паков, D6). Доступ по приоритету:

- бот установки: служебный доступ официального репозитория в режиме форка (`fork_mode`). Push только в форк бота,
  PR из форка в официальный репозиторий; автор коммита человек с noreply-адресом Студии. Только с правом «Автор
  шаблонов», админ может выключить, лимит предложений на человека в сутки, каждое использование в журнале;
- свой токен человека: обычный поток T6 с форком в его аккаунт;
- ни того, ни другого: интерфейс объясняет, какой токен выпустить.

Перед первой отправкой из официального пространства человек подтверждает, что вклад публичен и идёт под лицензией
репозитория (`license_accepted_at`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.pack_studio.entities import PackWorkspace, WorkspaceKind
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.official import (
    BOT_WINDOW,
    DAILY_LIMIT_MAX,
    BotQuota,
    BotSettings,
    OfficialRepo,
)
from hse_doc_studio.core.pack_studio.protocols import (
    IBotProposalCounter,
    IOfficialSettingsStore,
    IServiceAccessRepository,
    ServiceAccess,
)
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess
from hse_doc_studio.use_cases.pack_studio.workspaces import (
    CreateWorkspaceInput,
    PackWorkspaceService,
    WorkspaceView,
    owner_of,
)

AUDIT_LICENSE = "pack_studio.official_license_accepted"
AUDIT_OFFICIAL_UPDATE = "pack_studio.official_update"
OFFICIAL_LABEL = "Официальные паки"


class OfficialAccess(StrEnum):
    bot = "bot"
    token = "token"  # noqa: S105 — вид доступа, не секрет


class BotUnavailable(StrEnum):
    """Почему вклад через бота недоступен: локальная Студия, админ не задал доступ бота, выключил, нет права."""

    local = "local"
    not_configured = "not_configured"
    disabled = "disabled"
    no_right = "no_right"


@dataclass(frozen=True)
class BotView:
    available: bool
    reason: BotUnavailable | None
    quota: BotQuota | None


@dataclass(frozen=True)
class OfficialInfo:
    repo: OfficialRepo | None
    bot: BotView
    # Уже созданное официальное пространство человека: кнопка его открывает.
    workspace_id: UUID | None


@dataclass(frozen=True)
class OfficialAdminView:
    repo: OfficialRepo | None
    settings: BotSettings
    default_daily_limit: int
    # Служебный доступ официального репозитория, если задан (в режиме форка это бот).
    service_access: ServiceAccess | None


def _now() -> datetime:
    return datetime.now(UTC)


class OfficialPacks:
    def __init__(  # noqa: PLR0913 — порты и настройки установки
        self,
        repo: OfficialRepo | None,
        workspaces: PackWorkspaceService,
        access: PackStudioAccess,
        settings: IOfficialSettingsStore | None,
        *,
        default_daily_limit: int,
        service_access: IServiceAccessRepository | None = None,
        counter: IBotProposalCounter | None = None,
        audit: IAuditLog | None = None,
    ) -> None:
        self._repo = repo
        self._workspaces = workspaces
        self._access = access
        self._settings = settings
        self._default_limit = default_daily_limit
        self._service = service_access
        self._counter = counter
        self._audit = audit

    @property
    def repo(self) -> OfficialRepo | None:
        return self._repo

    # ── для людей ──

    async def info(self, actor: Actor) -> OfficialInfo:
        existing = await self._existing(actor) if self._repo is not None else None
        return OfficialInfo(repo=self._repo, bot=await self._bot_view(actor), workspace_id=existing)

    async def open(
        self, actor: Actor, access: OfficialAccess, credential_id: UUID | None
    ) -> tuple[WorkspaceView, bool]:
        """Пространство над официальным репозиторием: уже созданное или новое. Второе значение: создано ли сейчас."""
        repo = self._require_repo()
        existing = await self._existing(actor)
        if existing is not None:
            return await self._workspaces.get(actor, existing), False
        if access is OfficialAccess.bot:
            view = await self._bot_view(actor)
            if not view.available:
                raise PackStudioError(PackStudioErrorCode.official_bot_unavailable, reason=view.reason)
        created = await self._workspaces.create(
            actor,
            CreateWorkspaceInput(
                kind=WorkspaceKind.git,
                label=OFFICIAL_LABEL,
                url=repo.url,
                credential_id=credential_id if access is OfficialAccess.token else None,
                base_branch=repo.base_branch,
                service_access=access is OfficialAccess.bot,
                packs_path=repo.packs_path,
            ),
        )
        return created, True

    # ── для git рабочего пространства (PackGitService) ──

    def is_official(self, ws: PackWorkspace) -> bool:
        return self._repo is not None and self._repo.matches(ws.remote_url)

    async def bot_access_of(self, ws: PackWorkspace) -> ServiceAccess | None:
        """Служебный доступ пространства в режиме форка (бот); у личного доступа и прямого служебного None."""
        if ws.service_access_id is None or self._service is None:
            return None
        found = await self._service.get(ws.service_access_id)
        return found if found is not None and found.fork_mode else None

    async def remember_bot_fork(self, access_id: UUID, fork_url: str) -> None:
        """Форк бота, найденный или созданный его токеном при первой отправке, запоминается в служебном доступе."""
        if self._service is not None:
            await self._service.set_fork_url(access_id, fork_url)

    async def require_bot_quota(self, actor: Actor) -> BotQuota:
        """Перед отправкой через бота: вклад включён и лимит на человека в сутки не исчерпан."""
        settings = await self.bot_settings()
        if not settings.enabled:
            raise PackStudioError(PackStudioErrorCode.official_bot_unavailable, reason=BotUnavailable.disabled)
        quota = await self._quota(actor, settings)
        if quota.left <= 0:
            raise PackStudioError(PackStudioErrorCode.proposal_limit, limit=quota.limit)
        return quota

    async def accept_license(self, actor: Actor, ws: PackWorkspace, *, accepted: bool) -> PackWorkspace:
        """Согласие с лицензией перед первой отправкой из официального пространства (4.7)."""
        if not self.is_official(ws) or ws.license_accepted_at is not None:
            return ws
        repo = self._require_repo()
        if not accepted:
            raise PackStudioError(
                PackStudioErrorCode.license_consent_required,
                license=repo.license,
                license_url=repo.license_url,
                contributing_url=repo.contributing_url,
            )
        saved = await self._workspaces.save(replace(ws, license_accepted_at=_now()))
        if self._audit is not None:
            await self._audit.record(
                AUDIT_LICENSE,
                actor_id=actor.id,
                target=str(ws.id),
                details={"url": repo.url, "license": repo.license},
            )
        return saved

    # ── настройки бота ──

    async def bot_settings(self) -> BotSettings:
        enabled, limit = (None, None) if self._settings is None else await self._settings.get()
        return BotSettings(
            enabled=True if enabled is None else enabled,
            daily_limit=self._default_limit if limit is None else limit,
        )

    async def official_service_access(self) -> ServiceAccess | None:
        if self._repo is None or self._service is None:
            return None
        return await self._service.find(self._repo.key)

    async def admin_view(self) -> OfficialAdminView:
        return OfficialAdminView(
            repo=self._repo,
            settings=await self.bot_settings(),
            default_daily_limit=self._default_limit,
            service_access=await self.official_service_access(),
        )

    async def update_settings(self, admin_id: str, *, enabled: bool, daily_limit: int) -> OfficialAdminView:
        if self._settings is None:
            raise PackStudioError(PackStudioErrorCode.official_bot_unavailable, reason=BotUnavailable.local)
        limit = min(max(daily_limit, 1), DAILY_LIMIT_MAX)
        await self._settings.set(enabled=enabled, daily_limit=limit)
        if self._audit is not None:
            await self._audit.record(
                AUDIT_OFFICIAL_UPDATE, actor_id=admin_id, details={"bot_enabled": enabled, "daily_limit": limit}
            )
        return await self.admin_view()

    # ── служебное ──

    def _require_repo(self) -> OfficialRepo:
        if self._repo is None:
            raise PackStudioError(PackStudioErrorCode.official_unavailable)
        return self._repo

    async def _existing(self, actor: Actor) -> UUID | None:
        views = await self._workspaces.list(actor)
        official = [v.workspace for v in views if self.is_official(v.workspace)]
        return max(official, key=lambda ws: ws.created_at).id if official else None

    async def _bot_view(self, actor: Actor) -> BotView:
        if self._service is None or actor.is_local:
            return BotView(available=False, reason=BotUnavailable.local, quota=None)
        found = await self.official_service_access()
        if found is None or not found.fork_mode:
            return BotView(available=False, reason=BotUnavailable.not_configured, quota=None)
        settings = await self.bot_settings()
        if not settings.enabled:
            return BotView(available=False, reason=BotUnavailable.disabled, quota=None)
        if not await self._access.has_right(actor):
            return BotView(available=False, reason=BotUnavailable.no_right, quota=None)
        return BotView(available=True, reason=None, quota=await self._quota(actor, settings))

    async def _quota(self, actor: Actor, settings: BotSettings) -> BotQuota:
        owner = owner_of(actor)
        if self._counter is None or owner is None:
            return BotQuota(limit=settings.daily_limit, used=0)
        used = await self._counter.count_since(owner, _now() - BOT_WINDOW)
        return BotQuota(limit=settings.daily_limit, used=used)
