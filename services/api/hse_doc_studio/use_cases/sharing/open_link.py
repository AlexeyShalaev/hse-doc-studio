"""Открытие ссылки: превью, пароль с паузой, имя гостя, вход, гостевая сессия, визиты и ссылочное право.

Несуществующая, отозванная, истёкшая и запрещённая политикой ссылки неразличимы (`inactive`). Пароль
проверяется до того, как ответ назовёт проект или роль (S4). Вошедший получает ссылочное право, гость
получает гостевую сессию (cookie `hse_guest`, S1). Аудит переходов агрегированный (S9).
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal

from hse_doc_studio.core.access.entities import Actor, ActorKind, ProjectAcl
from hse_doc_studio.core.access.links import (
    GUEST_NAME_MAX,
    PASSWORD_MAX,
    GuestSession,
    IGuestSessionRepository,
    IShareLinkStore,
    LinkPreviewState,
    LinkProject,
    LinkRole,
    ShareLink,
    clean_text,
    hash_secret,
    looks_like_link_token,
    new_guest_session_id,
    password_delay_s,
)
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.access.resolution import ROLE_ORDER
from hse_doc_studio.core.access.sharing_policy import (
    ISharingPolicyReader,
    OrgLinksMode,
    SharingPolicy,
    guest_may_use,
    link_usable,
    login_forced,
)
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, ILoginAttemptRepository, IPasswordHasher
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork

GUEST_TOUCH_INTERVAL = timedelta(minutes=5)
_FAILED_AUDIT_INTERVAL = timedelta(minutes=15)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class LinkPreview:
    state: LinkPreviewState
    project_name: str | None = None
    owner_name: str | None = None
    role: LinkRole | None = None
    show_sources: bool = False
    guest_name_required: bool = False
    signed_in: bool = False


@dataclass(frozen=True)
class OpenedLink:
    project_id: str
    mode: Literal["guest", "user"]
    role: LinkRole
    show_sources: bool
    landing: Literal["workspace", "view"]
    # Секрет новой гостевой сессии для cookie; None, если сессия уже была или открыл вошедший.
    guest_secret: str | None = None


@dataclass(frozen=True)
class GuestLinkView:
    project_id: str
    project_name: str
    link_label: str
    role: LinkRole
    show_sources: bool


@dataclass(frozen=True)
class GuestInfoView:
    name: str | None
    links: list[GuestLinkView]


@dataclass(frozen=True)
class _Resolved:
    link: ShareLink
    project: LinkProject
    policy: SharingPolicy


def landing_of(link: ShareLink) -> Literal["workspace", "view"]:
    return "workspace" if link.sources_open else "view"


class GuestSessionService:
    """Гостевые сессии: поиск по секрету cookie со скользящим сроком и создание новой."""

    def __init__(
        self,
        sessions: IGuestSessionRepository,
        *,
        lifetime: timedelta = timedelta(days=30),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._sessions = sessions
        self._lifetime = lifetime
        self._clock = clock

    @property
    def lifetime(self) -> timedelta:
        return self._lifetime

    async def resolve(self, secret: str | None) -> GuestSession | None:
        if not secret:
            return None
        now = self._clock()
        session = await self._sessions.get_by_secret_hash(hash_secret(secret), now)
        if session is None:
            return None
        if now - session.last_seen_at >= GUEST_TOUCH_INTERVAL:
            await self._sessions.touch(session.id, now, now + self._lifetime)
        return session

    async def create(self, name: str | None, ip: str | None, user_agent: str) -> tuple[GuestSession, str]:
        now = self._clock()
        secret = secrets.token_urlsafe(32)
        session = GuestSession(
            id=new_guest_session_id(),
            name=name,
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._lifetime,
            csrf_token=secrets.token_urlsafe(32),
        )
        await self._sessions.create(session, hash_secret(secret), ip, user_agent)
        return session, secret


class ShareLinkResolver:
    """Ссылка по токену с проектом и текущей политикой; неподходящий токен и недействующая ссылка дают None."""

    def __init__(
        self,
        store: IShareLinkStore,
        policy: ISharingPolicyReader,
        orgs: IOrgRepository,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._store = store
        self._policy = policy
        self._orgs = orgs
        self._clock = clock

    async def resolve(self, token: str) -> _Resolved | None:
        if not looks_like_link_token(token):
            return None
        link = await self._store.get_by_token_hash(hash_secret(token))
        if link is None:
            return None
        project = await self._store.project(link.project_id)
        if project is None:
            return None
        policy = await self._policy.for_project(project.id)
        if not link_usable(link, self._clock(), policy, project_nda=project.nda):
            return None
        return _Resolved(link, project, policy)

    async def is_org_member(self, project: LinkProject, user_id: str) -> bool:
        if project.owner_org_id is None:
            return False
        return await self._orgs.get_member(project.owner_org_id, user_id) is not None


def _signed_in_user(actor: Actor | None) -> str | None:
    if actor is not None and actor.kind is ActorKind.user and actor.id is not None:
        return actor.id
    return None


def _needs_login(found: _Resolved) -> bool:
    return found.link.require_login or login_forced(found.policy, project_nda=found.project.nda)


class PreviewShareLinkUC:
    def __init__(self, resolver: ShareLinkResolver) -> None:
        self._resolver = resolver

    async def execute(self, token: str, actor: Actor | None) -> LinkPreview:
        user_id = _signed_in_user(actor)
        found = await self._resolver.resolve(token)
        if found is None:
            return LinkPreview(LinkPreviewState.inactive, signed_in=user_id is not None)
        link, project = found.link, found.project
        if link.has_password:
            return LinkPreview(LinkPreviewState.password_required, signed_in=user_id is not None)
        details = {
            "project_name": project.name,
            "owner_name": project.owner_name,
            "role": link.role,
            "show_sources": link.sources_open,
            "signed_in": user_id is not None,
        }
        if found.policy.org_mode is OrgLinksMode.org_only and (
            user_id is None or not await self._resolver.is_org_member(project, user_id)
        ):
            return LinkPreview(LinkPreviewState.org_only, **details)  # type: ignore[arg-type]
        if user_id is None and _needs_login(found):
            return LinkPreview(LinkPreviewState.login_required, **details)  # type: ignore[arg-type]
        return LinkPreview(
            LinkPreviewState.ok,
            guest_name_required=user_id is None and link.role is not LinkRole.reader,
            **details,  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class OpenRequest:
    token: str
    password: str | None
    guest_name: str | None
    actor: Actor | None
    guest: GuestSession | None
    ip: str | None
    user_agent: str


class OpenShareLinkUC:
    def __init__(  # noqa: PLR0913 — зависимости открытия ссылки
        self,
        resolver: ShareLinkResolver,
        store: IShareLinkStore,
        guests: IGuestSessionRepository,
        guest_sessions: GuestSessionService,
        acl: IProjectAclRepository,
        hasher: IPasswordHasher,
        attempts: ILoginAttemptRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._resolver = resolver
        self._store = store
        self._guests = guests
        self._guest_sessions = guest_sessions
        self._acl = acl
        self._hasher = hasher
        self._attempts = attempts
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, req: OpenRequest) -> OpenedLink:
        found = await self._resolver.resolve(req.token)
        if found is None:
            raise IdentityError(IdentityErrorCode.link_inactive)
        link, project = found.link, found.project
        await self._check_password(link, req.password, req.ip)
        user_id = _signed_in_user(req.actor)
        if user_id is not None and req.actor is not None:
            return await self._open_as_user(found, req.actor, user_id, req.ip)
        if _needs_login(found) or not guest_may_use(link, found.policy, project_nda=project.nda):
            raise IdentityError(IdentityErrorCode.link_login_required)
        return await self._open_as_guest(found, req)

    async def _check_password(self, link: ShareLink, password: str | None, ip: str | None) -> None:
        if not link.has_password:
            return
        key = f"link:{link.id}:{ip or '-'}"
        now = self._clock()
        attempt = await self._attempts.get(key)
        if attempt is not None and attempt.next_allowed_at is not None and attempt.next_allowed_at > now:
            retry = max(1, int((attempt.next_allowed_at - now).total_seconds()))
            raise IdentityError(IdentityErrorCode.link_password_locked, retry_after_s=retry)
        link_secrets = await self._store.secrets_of(link.id)
        stored = link_secrets.password_hash if link_secrets else None
        if password and stored and len(password) <= PASSWORD_MAX and self._hasher.verify(password, stored):
            if attempt is not None:
                await self._attempts.reset(key)
            return
        previous = attempt.updated_at if attempt is not None else None
        async with self._uow.begin():
            await self._attempts.record_failure(key, now, lambda n: timedelta(seconds=password_delay_s(n)))
            if previous is None or now - previous >= _FAILED_AUDIT_INTERVAL:
                await self._audit.record(
                    "link.password_failed",
                    actor_id=None,
                    target=str(link.project_id),
                    details={"link_id": link.id, "ip": ip},
                )
        raise IdentityError(IdentityErrorCode.link_password_wrong)

    async def _open_as_user(self, found: _Resolved, actor: Actor, user_id: str, ip: str | None) -> OpenedLink:
        link, project = found.link, found.project
        if found.policy.org_mode is OrgLinksMode.org_only and not await self._resolver.is_org_member(project, user_id):
            raise IdentityError(IdentityErrorCode.link_org_only)
        now = self._clock()
        member = await self._acl.load_for(actor, project.id, include_links=False)
        async with self._uow.begin():
            if not _membership_covers(member, actor, link):
                await self._store.grant_user(link.id, user_id, project.id, now)
            await self._visit(link, "user", user_id, actor.name, ip, now)
        return OpenedLink(str(project.id), "user", link.role, link.sources_open, landing_of(link))

    async def _open_as_guest(self, found: _Resolved, req: OpenRequest) -> OpenedLink:
        link = found.link
        name = _guest_name(req.guest_name, required=link.role is not LinkRole.reader)
        now = self._clock()
        secret: str | None = None
        async with self._uow.begin():
            session = req.guest
            if session is None:
                session, secret = await self._guest_sessions.create(name, req.ip, req.user_agent)
            elif name is not None and name != session.name:
                await self._guests.rename(session.id, name)
            await self._guests.attach_link(session.id, link.id, link.project_id, now)
            await self._visit(link, "guest", session.id, name or session.name, req.ip, now)
        return OpenedLink(
            str(link.project_id), "guest", link.role, link.sources_open, landing_of(link), guest_secret=secret
        )

    async def _visit(  # noqa: PLR0913 — визит несёт всё, что видно в журнале переходов
        self,
        link: ShareLink,
        kind: Literal["guest", "user"],
        visitor_id: str,
        name: str | None,
        ip: str | None,
        now: datetime,
    ) -> None:
        record = await self._store.record_visit(link.id, kind, visitor_id, name, ip, now)
        await self._store.touch_opened(link.id, now)
        if record.first_today:
            await self._audit.record(
                "link.open",
                actor_id=visitor_id if kind == "user" else None,
                target=str(link.project_id),
                details={"link_id": link.id, "label": link.label, "visitor_kind": kind, "visitor_name": name},
            )


def _membership_covers(acl: ProjectAcl | None, actor: Actor, link: ShareLink) -> bool:
    """У человека уже есть членство с ролью не ниже роли ссылки: ссылочное право не нужно."""
    grant = acl.grant_for(actor) if acl is not None else None
    if grant is None:
        return False
    return ROLE_ORDER.index(grant.role) >= ROLE_ORDER.index(link.role.role)


def _guest_name(raw: str | None, *, required: bool) -> str | None:
    name = clean_text(raw, GUEST_NAME_MAX) if raw is not None else None
    if raw is not None and raw.strip() and name is None:
        raise IdentityError(IdentityErrorCode.guest_name_required)
    if required and name is None:
        raise IdentityError(IdentityErrorCode.guest_name_required)
    return name


class GuestInfoUC:
    """Шапка гостя: имя и действующие ссылки сессии (отозванные и закрытые политикой не показываются)."""

    def __init__(
        self,
        guests: IGuestSessionRepository,
        store: IShareLinkStore,
        policy: ISharingPolicyReader,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._guests = guests
        self._store = store
        self._policy = policy
        self._clock = clock

    async def execute(self, session: GuestSession) -> GuestInfoView:
        now = self._clock()
        views: list[GuestLinkView] = []
        for item in await self._guests.links_of(session.id):
            link = item.link
            project = await self._store.project(link.project_id)
            if project is None:
                continue
            policy = await self._policy.for_project(link.project_id)
            if not link_usable(link, now, policy, project_nda=project.nda):
                continue
            if not guest_may_use(link, policy, project_nda=project.nda):
                continue
            views.append(
                GuestLinkView(str(link.project_id), item.project_name, link.label, link.role, link.sources_open)
            )
        return GuestInfoView(session.name, views)


class UpdateGuestSessionUC:
    def __init__(self, guests: IGuestSessionRepository, info: GuestInfoUC) -> None:
        self._guests = guests
        self._info = info

    async def execute(self, session: GuestSession, name: str) -> GuestInfoView:
        cleaned = clean_text(name, GUEST_NAME_MAX)
        if cleaned is None:
            raise IdentityError(IdentityErrorCode.guest_name_required)
        await self._guests.rename(session.id, cleaned)
        return await self._info.execute(replace(session, name=cleaned))


class LeaveGuestSessionUC:
    def __init__(self, guests: IGuestSessionRepository) -> None:
        self._guests = guests

    async def execute(self, session: GuestSession) -> None:
        await self._guests.delete(session.id)
