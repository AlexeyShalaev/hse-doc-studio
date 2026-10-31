"""Ссылки проекта глазами владельца и редактора с правом делиться: список, создание, правка, перевыпуск, отзыв.

Гард маршрута уже проверил `SHARE`. Здесь пределы роли (создатель, установка, организация), принуждение входа
(NDA, «только участникам организации»), лимит ссылок, S8 (редактор видит и правит только свои) и аудит.
Чужая и несуществующая ссылка неразличимы (404).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, ActorKind, Grant, Role
from hse_doc_studio.core.access.links import (
    EXPIRY_DAYS_MAX,
    LABEL_MAX,
    MAX_ACTIVE_LINKS_PER_PROJECT,
    PASSWORD_MAX,
    PASSWORD_MIN,
    REVOKED_VISIBLE_DAYS,
    IShareLinkStore,
    LinkBlockReason,
    LinkProject,
    LinkRole,
    LinkState,
    LinkVisit,
    LinkVisitStats,
    NewShareLinkRecord,
    RevokeReason,
    ShareLink,
    ShareLinkChanges,
    ShareLinkSecrets,
    clean_text,
    hash_secret,
    new_link_id,
    new_link_token,
    token_prefix_of,
)
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.access.sharing_policy import (
    ISharingPolicyReader,
    OrgLinksMode,
    SharingPolicy,
    cap_role,
    link_state,
    login_forced,
    max_role_for,
)
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IPasswordHasher
from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.core.uow import IUnitOfWork

LINK_PATH = "/s/"
_NO_VISITS = LinkVisitStats(visitors=0, opens=0, last_at=None)


def link_url(public_url: str | None, token: str) -> str:
    return f"{(public_url or '').rstrip('/')}{LINK_PATH}{token}"


def token_aad(link_id: str) -> str:
    return column_aad("share_links", "token_enc", link_id)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ShareLinkView:
    link: ShareLink
    url: str | None
    state: LinkState
    blocked_reason: LinkBlockReason | None
    editable: bool
    # Автор (id и имя); None, если смотрящий не владелец (он видит только свои ссылки).
    author: tuple[str, str] | None
    visits: LinkVisitStats


@dataclass(frozen=True)
class ShareLinkListing:
    items: list[ShareLinkView]
    can_create: bool
    max_role: LinkRole
    forced_login: bool
    revoked_count: int


@dataclass(frozen=True)
class NewShareLink:
    label: str
    role: LinkRole
    show_sources: bool = False
    require_login: bool = False
    password: str | None = None
    expires_in_days: int | None = None


@dataclass(frozen=True)
class ShareLinkPatch:
    label: str | None = None
    role: LinkRole | None = None
    show_sources: bool | None = None
    require_login: bool | None = None
    password: str | None = None
    clear_password: bool = False
    expires_in_days: int | None = None
    clear_expiry: bool = False


@dataclass(frozen=True)
class _Context:
    """Кто действует и над каким проектом: роль, политика, признак владельца."""

    actor_id: str
    project: LinkProject
    grant: Grant
    policy: SharingPolicy

    @property
    def is_owner(self) -> bool:
        return self.grant.role is Role.owner

    def may_edit(self, link: ShareLink) -> bool:
        return self.is_owner or link.created_by == self.actor_id


def _not_found() -> IdentityError:
    return IdentityError(IdentityErrorCode.not_found)


class ShareLinkService:
    """Общее для сценариев ссылок: загрузка контекста, вид ссылки с состоянием и адресом, проверки ввода."""

    def __init__(  # noqa: PLR0913 — зависимости сценариев ссылок
        self,
        store: IShareLinkStore,
        acl: IProjectAclRepository,
        policy: ISharingPolicyReader,
        cipher: ISecretCipher,
        hasher: IPasswordHasher,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        public_url: str | None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.store = store
        self.acl = acl
        self.policy = policy
        self.cipher = cipher
        self.hasher = hasher
        self.audit = audit
        self.uow = uow
        self.public_url = public_url
        self.clock = clock

    async def context(self, actor: Actor, project_id: UUID) -> _Context:
        if actor.kind is not ActorKind.user or actor.id is None:
            raise IdentityError(IdentityErrorCode.auth_required)
        project = await self.store.project(project_id)
        acl = await self.acl.load_for(actor, project_id, include_links=False)
        grant = acl.grant_for(actor) if acl is not None else None
        if project is None or grant is None:
            raise _not_found()
        return _Context(actor.id, project, grant, await self.policy.for_project(project_id))

    async def visible_link(self, ctx: _Context, link_id: str) -> ShareLink:
        link = await self.store.get(link_id)
        if link is None or link.project_id != ctx.project.id or not ctx.may_edit(link):
            raise _not_found()
        return link

    def url_of(self, link: ShareLink, secrets: ShareLinkSecrets | None) -> str | None:
        if secrets is None:
            return None
        token = self.cipher.decrypt(secrets.token_enc, aad=token_aad(link.id)).reveal()
        return link_url(self.public_url, token)

    async def view(
        self, ctx: _Context, link: ShareLink, *, names: dict[str, str], visits: LinkVisitStats | None = None
    ) -> ShareLinkView:
        now = self.clock()
        state, reason = link_state(link, now, ctx.policy, project_nda=ctx.project.nda)
        url = None
        if state in (LinkState.active, LinkState.blocked):
            url = self.url_of(link, await self.store.secrets_of(link.id))
        author = None
        if ctx.is_owner and link.created_by is not None:
            author = (link.created_by, names.get(link.created_by, ""))
        return ShareLinkView(
            link=link,
            url=url,
            state=state,
            blocked_reason=reason,
            editable=state is not LinkState.revoked and ctx.may_edit(link),
            author=author,
            visits=visits or _NO_VISITS,
        )

    async def single_view(self, ctx: _Context, link: ShareLink) -> ShareLinkView:
        names = await self.store.user_names([link.created_by] if link.created_by else [])
        stats = await self.store.visit_stats([link.id])
        return await self.view(ctx, link, names=names, visits=stats.get(link.id))

    def password_hash(self, password: str) -> str:
        if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
            raise IdentityError(IdentityErrorCode.link_password_invalid)
        return self.hasher.hash(password)

    def role_within_limits(self, ctx: _Context, role: LinkRole) -> LinkRole:
        capped = cap_role(role, creator=ctx.grant.role, policy=ctx.policy)
        if capped is None:
            raise IdentityError(IdentityErrorCode.link_role_too_high)
        return capped

    def expiry(self, days: int | None) -> datetime | None:
        if days is None:
            return None
        if not 1 <= days <= EXPIRY_DAYS_MAX:
            raise IdentityError(IdentityErrorCode.input_invalid)
        return self.clock() + timedelta(days=days)

    def require_links_allowed(self, ctx: _Context) -> None:
        if not ctx.policy.links_enabled or ctx.policy.org_mode is OrgLinksMode.off:
            raise IdentityError(IdentityErrorCode.links_disabled)

    def new_secrets(self, link_id: str, password_hash: str | None) -> tuple[ShareLinkSecrets, str]:
        token = new_link_token()
        token_enc = self.cipher.encrypt(Secret(token), aad=token_aad(link_id))
        return ShareLinkSecrets(password_hash=password_hash, token_hash=hash_secret(token), token_enc=token_enc), token

    async def record(self, action: str, ctx: _Context, link: ShareLink, **details: object) -> None:
        await self.audit.record(
            action,
            actor_id=ctx.actor_id,
            target=str(ctx.project.id),
            details={"link_id": link.id, "label": link.label, "role": link.role.value, **details},
        )


def _label(value: str) -> str:
    label = clean_text(value, LABEL_MAX)
    if label is None:
        raise IdentityError(IdentityErrorCode.input_invalid)
    return label


class ListShareLinksUC:
    def __init__(self, service: ShareLinkService) -> None:
        self._s = service

    async def execute(self, actor: Actor, project_id: UUID, *, include_revoked: bool = False) -> ShareLinkListing:
        ctx = await self._s.context(actor, project_id)
        created_by = None if ctx.is_owner else ctx.actor_id
        since = self._s.clock() - timedelta(days=REVOKED_VISIBLE_DAYS)
        links = await self._s.store.list_for_project(
            project_id, created_by=created_by, revoked_since=since if include_revoked else None
        )
        names = await self._s.store.user_names([x.created_by for x in links if x.created_by])
        stats = await self._s.store.visit_stats([x.id for x in links])
        items = [await self._s.view(ctx, link, names=names, visits=stats.get(link.id)) for link in links]
        return ShareLinkListing(
            items=items,
            can_create=ctx.policy.links_enabled and ctx.policy.org_mode is not OrgLinksMode.off,
            max_role=max_role_for(ctx.grant.role, ctx.policy),
            forced_login=login_forced(ctx.policy, project_nda=ctx.project.nda),
            revoked_count=await self._s.store.count_revoked(project_id, created_by=created_by, since=since),
        )


class CreateShareLinkUC:
    def __init__(self, service: ShareLinkService) -> None:
        self._s = service

    async def execute(self, actor: Actor, project_id: UUID, new: NewShareLink) -> tuple[ShareLinkView, str]:
        """Новая ссылка и её полный адрес (его же можно скопировать позже из списка)."""
        s = self._s
        ctx = await s.context(actor, project_id)
        s.require_links_allowed(ctx)
        role = s.role_within_limits(ctx, new.role)
        label = _label(new.label)
        password_hash = s.password_hash(new.password) if new.password else None
        now = s.clock()
        link_id = new_link_id()
        secrets, token = s.new_secrets(link_id, password_hash)
        link = ShareLink(
            id=link_id,
            project_id=project_id,
            label=label,
            role=role,
            show_sources=new.show_sources or role is not LinkRole.reader,
            # Политика принуждает вход тихо: ответ показывает итоговое значение.
            require_login=new.require_login or login_forced(ctx.policy, project_nda=ctx.project.nda),
            has_password=password_hash is not None,
            token_prefix=token_prefix_of(token),
            created_by=ctx.actor_id,
            created_at=now,
            updated_at=now,
            expires_at=s.expiry(new.expires_in_days),
            revoked_at=None,
            revoke_reason=None,
            replaced_by=None,
            last_opened_at=None,
        )
        async with s.uow.begin():
            if await s.store.count_active(project_id, now) >= MAX_ACTIVE_LINKS_PER_PROJECT:
                raise IdentityError(IdentityErrorCode.link_limit)
            await s.store.add(NewShareLinkRecord(link, secrets))
            await s.record(
                "link.create",
                ctx,
                link,
                show_sources=link.show_sources,
                require_login=link.require_login,
                has_password=link.has_password,
                expires_at=link.expires_at.isoformat() if link.expires_at else None,
            )
        return await s.single_view(ctx, link), link_url(s.public_url, token)


class UpdateShareLinkUC:
    def __init__(self, service: ShareLinkService) -> None:
        self._s = service

    async def execute(self, actor: Actor, project_id: UUID, link_id: str, patch: ShareLinkPatch) -> ShareLinkView:
        s = self._s
        ctx = await s.context(actor, project_id)
        link = await s.visible_link(ctx, link_id)
        if link.revoked_at is not None:
            raise IdentityError(IdentityErrorCode.link_revoked)
        changes, changed = self._changes(ctx, link, patch)
        if not changed:
            return await s.single_view(ctx, link)
        async with s.uow.begin():
            updated = await s.store.update(link.id, changes, s.clock())
            if updated is None:
                raise IdentityError(IdentityErrorCode.link_revoked)
            # Пароль в журнал не попадает: только факт смены.
            await s.record("link.update", ctx, updated, changed=sorted(changed))
        return await s.single_view(ctx, updated)

    def _changes(  # noqa: C901 — по ветке на каждое поле правки
        self, ctx: _Context, link: ShareLink, patch: ShareLinkPatch
    ) -> tuple[ShareLinkChanges, set[str]]:
        """Что записать и имена изменённых полей (для журнала); пустой набор значит «ничего не менять»."""
        s = self._s
        values: dict[str, object] = {}
        if patch.label is not None and (label := _label(patch.label)) != link.label:
            values["label"] = label
        role = link.role
        if patch.role is not None and patch.role is not link.role:
            role = values["role"] = s.role_within_limits(ctx, patch.role)
        show_sources = patch.show_sources if patch.show_sources is not None else link.show_sources
        show_sources = show_sources or role is not LinkRole.reader
        if show_sources != link.show_sources:
            values["show_sources"] = show_sources
        if patch.require_login is not None:
            wanted = patch.require_login or login_forced(ctx.policy, project_nda=ctx.project.nda)
            if wanted != link.require_login:
                values["require_login"] = wanted
        if patch.clear_password and link.has_password:
            values.update(set_password=True, password_hash=None)
        elif patch.password:
            values.update(set_password=True, password_hash=s.password_hash(patch.password))
        if patch.clear_expiry and link.expires_at is not None:
            values.update(set_expiry=True, expires_at=None)
        elif patch.expires_in_days is not None:
            values.update(set_expiry=True, expires_at=s.expiry(patch.expires_in_days))
        changed = {"password" if k == "password_hash" else k for k in values if not k.startswith("set_")}
        return ShareLinkChanges(**values), changed  # type: ignore[arg-type]


class RotateShareLinkUC:
    def __init__(self, service: ShareLinkService) -> None:
        self._s = service

    async def execute(self, actor: Actor, project_id: UUID, link_id: str) -> tuple[ShareLinkView, str]:
        """Новая ссылка с теми же настройками и новым токеном; старая отозвана с `replaced_by`."""
        s = self._s
        ctx = await s.context(actor, project_id)
        old = await s.visible_link(ctx, link_id)
        if old.revoked_at is not None:
            raise IdentityError(IdentityErrorCode.link_revoked)
        old_secrets = await s.store.secrets_of(old.id)
        now = s.clock()
        new_id = new_link_id()
        secrets, token = s.new_secrets(new_id, old_secrets.password_hash if old_secrets else None)
        new = replace(
            old,
            id=new_id,
            token_prefix=token_prefix_of(token),
            created_at=now,
            updated_at=now,
            last_opened_at=None,
        )
        async with s.uow.begin():
            if not await s.store.revoke(
                old.id, by=ctx.actor_id, reason=RevokeReason.rotated, now=now, replaced_by=new_id
            ):
                raise IdentityError(IdentityErrorCode.link_revoked)
            await s.store.add(NewShareLinkRecord(new, secrets))
            await s.record("link.rotate", ctx, new, replaced=old.id)
        return await s.single_view(ctx, new), link_url(s.public_url, token)


class RevokeShareLinkUC:
    def __init__(self, service: ShareLinkService) -> None:
        self._s = service

    async def execute(self, actor: Actor, project_id: UUID, link_id: str) -> None:
        """Повторный отзыв ничего не меняет и не ошибка (204)."""
        s = self._s
        ctx = await s.context(actor, project_id)
        link = await s.visible_link(ctx, link_id)
        async with s.uow.begin():
            if await s.store.revoke(link.id, by=ctx.actor_id, reason=RevokeReason.manual, now=s.clock()):
                await s.record("link.revoke", ctx, link)


class ListLinkVisitsUC:
    def __init__(self, service: ShareLinkService) -> None:
        self._s = service

    async def execute(self, actor: Actor, project_id: UUID, link_id: str, window: Window) -> Found[LinkVisit]:
        ctx = await self._s.context(actor, project_id)
        link = await self._s.visible_link(ctx, link_id)
        return await self._s.store.visits(link.id, window)
