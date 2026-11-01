"""Приглашения в проект (D7, D8, S10–S12): создание, повтор, отзыв, списки, принятие и отказ, ссылка из письма.

Приглашение существующему человеку видно ему во «Входящих» и даёт доступ только после «Принять». Приглашение на
почту несёт секретную ссылку `<public_url>/project-invite/<token>`; принять его может только аккаунт с
подтверждённой совпадающей почтой (S11). Права проверяет гард маршрута (ACCESS_MANAGE); сценарий дополнительно
ограничивает выдаваемое правами самого приглашающего.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, Grant, Role
from hse_doc_studio.core.access.repositories import (
    IProjectAccessDirectory,
    IProjectAclRepository,
    IProjectMemberRepository,
    ProjectMemberGrant,
)
from hse_doc_studio.core.identity.entities import RegistrationInvite, RegistrationMode, User
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token, is_valid_email, new_token, normalize_email
from hse_doc_studio.core.identity.protocols import IAuditLog, IRegistrationInviteRepository, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import (
    GRANTABLE_ROLES,
    INVITATION_TOKEN_PREFIX,
    MAX_INVITATION_DAYS,
    MAX_PENDING_INVITATIONS,
    MAX_RESENDS,
    MIN_INVITATION_DAYS,
    RESEND_INTERVAL,
    InvitationDelivery,
    InvitationStatus,
    InvitationView,
    MemberTerms,
    MyInvitationView,
    NotificationKind,
    NotificationPayload,
    ProjectCard,
    ProjectInvitation,
    mask_email,
    role_at_most,
    stronger,
)
from hse_doc_studio.core.invitations.policy import email_allowed_for_org
from hse_doc_studio.core.invitations.protocols import (
    INotificationMailer,
    INotifier,
    IProjectCards,
    IProjectInvitationRepository,
    IProjectMemberLookup,
    IProjectPersonas,
)
from hse_doc_studio.core.listing import Found, Window, clamp_limit
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
from hse_doc_studio.use_cases.orgs.access import user_id_of

_log = logging.getLogger(__name__)

INVITE_LINK_PATH = "/project-invite"

SignupAllowed = Callable[[], Awaitable[bool]]


@dataclass(frozen=True)
class NewInvitation:
    terms: MemberTerms
    user_id: str | None = None
    email: str | None = None
    message: str | None = None
    expires_in_days: int = 7


@dataclass(frozen=True)
class InvitationCreated:
    view: InvitationView
    delivery: InvitationDelivery
    link: str | None


@dataclass(frozen=True)
class InvitationPreview:
    state: Literal["ok", "expired", "used", "invalid"]
    project_name: str | None = None
    inviter_name: str | None = None
    role: Role | None = None
    email_hint: str | None = None
    registration_token: str | None = None


def invitation_link(public_url: str | None, token: str) -> str:
    return f"{(public_url or '').rstrip('/')}{INVITE_LINK_PATH}/{token}"


def new_invitation_token() -> str:
    return INVITATION_TOKEN_PREFIX + new_token()


async def actor_grant(acl: IProjectAclRepository, actor: Actor, project_id: UUID) -> Grant:
    """Право приглашающего на проект; без права 404, без права решать доступ 403."""
    loaded = await acl.load_for(actor, project_id)
    grant = loaded.grant_for(actor) if loaded is not None else None
    if grant is None:
        raise IdentityError(IdentityErrorCode.not_found)
    if grant.role is not Role.owner and not (grant.role is Role.editor and grant.can_share):
        raise IdentityError(IdentityErrorCode.forbidden)
    return grant


def check_terms_within(terms: MemberTerms, grant: Grant) -> None:
    """Роль и флаги не выше своих (6.1 п. 1): редактор без права «править всё» его не выдаёт."""
    if terms.role not in GRANTABLE_ROLES:
        raise IdentityError(IdentityErrorCode.input_invalid)
    if not role_at_most(terms.role, grant.role):
        raise IdentityError(IdentityErrorCode.invitation_role_too_high)
    if grant.role is not Role.owner and (
        (terms.can_share and not grant.can_share) or (terms.can_edit_all and not grant.can_edit_all)
    ):
        raise IdentityError(IdentityErrorCode.invitation_role_too_high)


async def check_persona(personas: IProjectPersonas, project_id: UUID, persona: str | None) -> None:
    if persona is None:
        return
    known = await personas.personas(project_id)
    if known is None or persona not in known:
        raise IdentityError(IdentityErrorCode.persona_unknown)


def _payload(
    card: ProjectCard, actor_name: str | None, invitation: ProjectInvitation, outcome: str | None = None
) -> NotificationPayload:
    return NotificationPayload(
        project_id=str(card.id),
        project_name=card.name,
        actor_name=actor_name,
        role=invitation.terms.role.value,
        ref_id=invitation.id,
        outcome=outcome,
    )


def member_grant(user_id: str, terms: MemberTerms) -> ProjectMemberGrant:
    return ProjectMemberGrant(
        principal_kind="user",
        principal_id=user_id,
        role=terms.role,
        persona=terms.persona,
        can_share=terms.can_share,
        show_sources=terms.show_sources or terms.role is not Role.reader,
        can_edit_all=terms.can_edit_all,
    )


class _Base:
    def __init__(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._invitations = invitations
        self._cards = cards
        self._users = users
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def _card(self, project_id: UUID) -> ProjectCard:
        card = await self._cards.card(project_id)
        if card is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return card

    async def _name(self, user_id: str | None) -> str | None:
        if user_id is None:
            return None
        user = await self._users.get(user_id)
        return user.name if user else None

    async def _view(self, invitation: ProjectInvitation) -> InvitationView:
        return InvitationView(
            invitation, await self._name(invitation.invitee_user_id), await self._name(invitation.invited_by)
        )


class CreateInvitationUC(_Base):
    def __init__(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        acl: IProjectAclRepository,
        directory: IProjectAccessDirectory,
        members: IProjectMemberLookup,
        personas: IProjectPersonas,
        orgs: IOrgRepository,
        auth_settings: AuthSettingsService,
        registration_invites: IRegistrationInviteRepository,
        notifier: INotifier,
        mailer: INotificationMailer,
        signup_allowed: SignupAllowed,
        public_url: str | None = None,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(invitations, cards, users, audit, uow, clock)
        self._acl = acl
        self._directory = directory
        self._members = members
        self._personas = personas
        self._orgs = orgs
        self._auth_settings = auth_settings
        self._registration_invites = registration_invites
        self._notifier = notifier
        self._mailer = mailer
        self._signup_allowed = signup_allowed
        self._public_url = public_url

    async def execute(self, actor: Actor, project_id: UUID, new: NewInvitation) -> InvitationCreated:
        actor_id = user_id_of(actor)
        if (new.user_id is None) == (new.email is None):
            raise IdentityError(IdentityErrorCode.input_invalid)
        if not MIN_INVITATION_DAYS <= new.expires_in_days <= MAX_INVITATION_DAYS:
            raise IdentityError(IdentityErrorCode.input_invalid)
        grant = await actor_grant(self._acl, actor, project_id)
        card = await self._card(project_id)
        check_terms_within(new.terms, grant)
        await check_persona(self._personas, project_id, new.terms.persona)
        now = self._clock()
        if await self._invitations.count_pending(project_id, now) >= MAX_PENDING_INVITATIONS:
            raise IdentityError(IdentityErrorCode.invitation_limit)
        if new.user_id is not None:
            return await self._invite_user(actor, actor_id, card, new, new.user_id, now)
        return await self._invite_email(actor, actor_id, card, new, str(new.email), now)

    async def _ensure_not_member(self, card: ProjectCard, user_id: str) -> None:
        if user_id == card.owner_user_id or await self._members.direct_user_role(card.id, user_id) is not None:
            raise IdentityError(IdentityErrorCode.already_member)

    async def _ensure_no_pending(self, existing: ProjectInvitation | None, now: datetime) -> None:
        if existing is None:
            return
        if existing.expires_at > now:
            raise IdentityError(IdentityErrorCode.invitation_pending, extra={"invitation_id": existing.id})
        # Просроченное ожидающее не держит место: его заменяет новое.
        await self._invitations.update(replace(existing, status=InvitationStatus.revoked, decided_at=now))

    async def _invite_user(
        self, actor: Actor, actor_id: str, card: ProjectCard, new: NewInvitation, user_id: str, now: datetime
    ) -> InvitationCreated:
        # Только круг, которому приглашающий вправе открыть проект; иначе ответ как у несуществующего (T11).
        if not await self._directory.can_share_with(card.id, actor_id, user_id):
            raise IdentityError(IdentityErrorCode.not_found)
        user = await self._users.get(user_id)
        if user is None or not user.can_sign_in:
            raise IdentityError(IdentityErrorCode.not_found)
        await self._ensure_not_member(card, user_id)
        invitation = self._new(card, actor_id, new, now, user_id=user_id, email=None, token_hash=None)
        async with self._uow.begin():
            await self._ensure_no_pending(await self._invitations.pending_for_user(card.id, user_id), now)
            await self._invitations.add(invitation)
            await self._record(actor_id, invitation, user.email_normalized)
            await self._notifier.notify(
                user_id,
                NotificationKind.project_invitation,
                _payload(card, actor.name or await self._name(actor_id), invitation),
                dedupe_key=f"inv:{invitation.id}",
            )
        delivery: InvitationDelivery = "email" if self._mailer.enabled and user.email_verified else "inbox"
        return InvitationCreated(await self._view(invitation), delivery, None)

    async def _invite_email(
        self, actor: Actor, actor_id: str, card: ProjectCard, new: NewInvitation, raw_email: str, now: datetime
    ) -> InvitationCreated:
        email = await self._checked_email(card, raw_email)
        bound = await self._bound_account(card, email)
        registration = await self._registration_mode() if bound is None and await self._no_account(email) else False
        token = new_invitation_token()
        invitation = self._new(
            card,
            actor_id,
            new,
            now,
            user_id=bound.id if bound else None,
            email=email,
            token_hash=hash_token(token),
            registration_invite_id=hash_token(token)[:32] if registration else None,
        )
        async with self._uow.begin():
            await self._ensure_no_pending(await self._invitations.pending_for_email(card.id, email), now)
            if bound is not None:
                await self._ensure_no_pending(await self._invitations.pending_for_user(card.id, bound.id), now)
            if registration:
                # S12: регистрационное приглашение с тем же секретом, что и ссылка приглашения в проект.
                await self._registration_invites.add(
                    RegistrationInvite(
                        token_hash=hash_token(token),
                        email=email,
                        created_by=actor_id,
                        expires_at=invitation.expires_at,
                        id=hash_token(token)[:32],
                    )
                )
            await self._invitations.add(invitation)
            await self._record(actor_id, invitation, email, registration=registration)
            if bound is not None:
                await self._notifier.notify(
                    bound.id,
                    NotificationKind.project_invitation,
                    _payload(card, actor.name or await self._name(actor_id), invitation),
                    dedupe_key=f"inv:{invitation.id}",
                )
        link = invitation_link(self._public_url, token)
        inviter = actor.name or await self._name(actor_id) or ""
        sent = await self._mailer.send_invitation(
            email,
            project_name=card.name,
            inviter_name=inviter,
            role=new.terms.role.value,
            link=link,
            message=new.message,
            locale=None,
        )
        # Ответ одинаков с аккаунтом и без (T11): решает только то, ушло ли письмо.
        return InvitationCreated(await self._view(invitation), "email" if sent else "manual", None if sent else link)

    async def _checked_email(self, card: ProjectCard, raw_email: str) -> str:
        if not is_valid_email(raw_email):
            raise IdentityError(IdentityErrorCode.input_invalid)
        email = normalize_email(raw_email)
        if card.owner_org_id is not None:
            org = await self._orgs.get(card.owner_org_id)
            if org is not None and not email_allowed_for_org(org.policies, email):
                raise IdentityError(IdentityErrorCode.external_invite_forbidden)
        return email

    async def _bound_account(self, card: ProjectCard, email: str) -> User | None:
        """Аккаунт с этой подтверждённой почтой: приглашение сразу привязывается к нему (6.1 п. 3)."""
        account = await self._users.get_by_email(email)
        if account is None or not account.email_verified or not account.can_sign_in:
            return None
        await self._ensure_not_member(card, account.id)
        return account

    async def _no_account(self, email: str) -> bool:
        return await self._users.get_by_email(email) is None

    async def _registration_mode(self) -> bool:
        """True, если для адреса без аккаунта нужно регистрационное приглашение (S12)."""
        mode = (await self._auth_settings.effective()).registration_mode
        if mode is RegistrationMode.closed:
            raise IdentityError(IdentityErrorCode.invitee_cannot_register)
        if mode is RegistrationMode.invite:
            if not await self._signup_allowed():
                raise IdentityError(IdentityErrorCode.invitee_cannot_register)
            return True
        return False

    def _new(
        self,
        card: ProjectCard,
        actor_id: str,
        new: NewInvitation,
        now: datetime,
        *,
        user_id: str | None,
        email: str | None,
        token_hash: str | None,
        registration_invite_id: str | None = None,
    ) -> ProjectInvitation:
        return ProjectInvitation(
            id=f"inv_{uuid.uuid4().hex}",
            project_id=card.id,
            invitee_user_id=user_id,
            invitee_email=email,
            terms=new.terms,
            message=(new.message or "").strip() or None,
            token_hash=token_hash,
            invited_by=actor_id,
            created_at=now,
            expires_at=now + timedelta(days=new.expires_in_days),
            status=InvitationStatus.pending,
            last_sent_at=now,
            registration_invite_id=registration_invite_id,
        )

    async def _record(
        self, actor_id: str, invitation: ProjectInvitation, email: str | None, *, registration: bool | None = None
    ) -> None:
        details: dict[str, object] = {
            "invitation_id": invitation.id,
            "role": invitation.terms.role.value,
            "email": mask_email(email),
        }
        if registration:
            details["registration"] = True
        await self._audit.record(
            "project.invitation.create", actor_id=actor_id, target=str(invitation.project_id), details=details
        )


class ResendInvitationUC(_Base):
    def __init__(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        acl: IProjectAclRepository,
        registration_invites: IRegistrationInviteRepository,
        notifier: INotifier,
        mailer: INotificationMailer,
        public_url: str | None = None,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(invitations, cards, users, audit, uow, clock)
        self._acl = acl
        self._registration_invites = registration_invites
        self._notifier = notifier
        self._mailer = mailer
        self._public_url = public_url

    async def execute(self, actor: Actor, project_id: UUID, invitation_id: str) -> InvitationCreated:
        actor_id = user_id_of(actor)
        await actor_grant(self._acl, actor, project_id)
        card = await self._card(project_id)
        now = self._clock()
        token: str | None = None
        async with self._uow.begin():
            current = await self._invitations.lock(invitation_id)
            if current is None or current.project_id != project_id:
                raise IdentityError(IdentityErrorCode.not_found)
            if current.status is not InvitationStatus.pending:
                raise IdentityError(IdentityErrorCode.invitation_not_pending)
            if current.sent_count > MAX_RESENDS or now - current.last_sent_at < RESEND_INTERVAL:
                raise IdentityError(IdentityErrorCode.invitation_resend_too_soon)
            period = current.expires_at - current.created_at
            updated = replace(current, sent_count=current.sent_count + 1, last_sent_at=now, expires_at=now + period)
            if current.invitee_email is not None:
                # Новый секрет: старая ссылка из письма перестаёт работать.
                token = new_invitation_token()
                updated = await self._rotate(updated, token, actor_id)
            await self._invitations.update(updated)
            await self._audit.record(
                "project.invitation.resend",
                actor_id=actor_id,
                target=str(project_id),
                details={"invitation_id": invitation_id, "sent_count": updated.sent_count},
            )
            if updated.invitee_user_id is not None:
                await self._notifier.notify(
                    updated.invitee_user_id,
                    NotificationKind.project_invitation,
                    _payload(card, actor.name or await self._name(actor_id), updated),
                    dedupe_key=f"inv:{updated.id}",
                )
        if token is None:
            delivery: InvitationDelivery = "email" if self._mailer.enabled else "inbox"
            return InvitationCreated(await self._view(updated), delivery, None)
        link = invitation_link(self._public_url, token)
        sent = await self._mailer.send_invitation(
            str(updated.invitee_email),
            project_name=card.name,
            inviter_name=actor.name or await self._name(actor_id) or "",
            role=updated.terms.role.value,
            link=link,
            message=updated.message,
            locale=None,
        )
        return InvitationCreated(await self._view(updated), "email" if sent else "manual", None if sent else link)

    async def _rotate(self, updated: ProjectInvitation, token: str, actor_id: str) -> ProjectInvitation:
        updated = replace(updated, token_hash=hash_token(token))
        if updated.registration_invite_id is None:
            return updated
        await self._registration_invites.revoke(updated.registration_invite_id)
        await self._registration_invites.add(
            RegistrationInvite(
                token_hash=hash_token(token),
                email=updated.invitee_email,
                created_by=actor_id,
                expires_at=updated.expires_at,
                id=hash_token(token)[:32],
            )
        )
        return replace(updated, registration_invite_id=hash_token(token)[:32])


class RevokeInvitationUC(_Base):
    def __init__(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        acl: IProjectAclRepository,
        registration_invites: IRegistrationInviteRepository,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(invitations, cards, users, audit, uow, clock)
        self._acl = acl
        self._registration_invites = registration_invites

    async def execute(self, actor: Actor, project_id: UUID, invitation_id: str) -> None:
        actor_id = user_id_of(actor)
        await actor_grant(self._acl, actor, project_id)
        async with self._uow.begin():
            current = await self._invitations.lock(invitation_id)
            if current is None or current.project_id != project_id:
                raise IdentityError(IdentityErrorCode.not_found)
            if current.status is not InvitationStatus.pending:
                return
            await self._invitations.update(replace(current, status=InvitationStatus.revoked, decided_at=self._clock()))
            if current.registration_invite_id is not None:
                await self._registration_invites.revoke(current.registration_invite_id)
            await self._audit.record(
                "project.invitation.revoke",
                actor_id=actor_id,
                target=str(project_id),
                details={"invitation_id": invitation_id},
            )


class ListProjectInvitationsUC:
    def __init__(self, invitations: IProjectInvitationRepository) -> None:
        self._invitations = invitations

    async def execute(self, project_id: UUID, *, pending_only: bool, window: Window) -> Found[InvitationView]:
        window = Window(clamp_limit(window.limit), max(0, window.offset))
        return await self._invitations.page_for_project(project_id, pending_only=pending_only, window=window)


class AttachInvitationsByEmailUC(_Base):
    """Приглашения на подтверждённую почту человека привязываются к нему и попадают во «Входящие»."""

    def __init__(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        notifier: INotifier,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(invitations, cards, users, audit, uow, clock)
        self._notifier = notifier

    async def on_email_verified(self, user_id: str, email_normalized: str) -> None:
        """Сбой привязки не должен ломать подтверждение почты: приглашения привяжутся при чтении «Входящих»."""
        try:
            await self.execute(user_id, email_normalized)
        except Exception:
            _log.exception("invitation attach failed")

    async def execute(self, user_id: str, email_normalized: str) -> int:
        async with self._uow.begin():
            attached = await self._invitations.attach_email(email_normalized, user_id)
            for invitation in attached:
                card = await self._cards.card(invitation.project_id)
                if card is None:
                    continue
                await self._notifier.notify(
                    user_id,
                    NotificationKind.project_invitation,
                    _payload(card, await self._name(invitation.invited_by), invitation),
                    dedupe_key=f"inv:{invitation.id}",
                )
        return len(attached)


class ListMyInvitationsUC:
    def __init__(self, invitations: IProjectInvitationRepository, attach: AttachInvitationsByEmailUC,
                 users: IUserRepository) -> None:  # fmt: skip
        self._invitations = invitations
        self._attach = attach
        self._users = users

    async def execute(self, actor: Actor) -> list[MyInvitationView]:
        user_id = user_id_of(actor)
        user = await self._users.get(user_id)
        if user is not None and user.email_verified:
            await self._attach.execute(user_id, user.email_normalized)
        return await self._invitations.list_for_user(user_id)


class _Decide(_Base):
    def __init__(
        self,
        invitations: IProjectInvitationRepository,
        cards: IProjectCards,
        users: IUserRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        *,
        members: IProjectMemberRepository,
        member_roles: IProjectMemberLookup,
        notifier: INotifier,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(invitations, cards, users, audit, uow, clock)
        self._members = members
        self._member_roles = member_roles
        self._notifier = notifier

    async def _decide(self, actor: Actor, invitation_id: str, accept: bool, *, by_token: bool) -> MyInvitationView:
        user_id = user_id_of(actor)
        now = self._clock()
        async with self._uow.begin():
            current = await self._invitations.lock(invitation_id)
            if current is None:
                raise IdentityError(IdentityErrorCode.not_found)
            current = await self._claim(current, user_id, by_token=by_token)
            if current.status is not InvitationStatus.pending:
                raise IdentityError(IdentityErrorCode.invitation_not_pending)
            if current.expires_at <= now:
                raise IdentityError(IdentityErrorCode.invitation_expired)
            card = await self._card(current.project_id)
            status = InvitationStatus.accepted if accept else InvitationStatus.declined
            decided = replace(current, status=status, decided_at=now, invitee_user_id=user_id)
            await self._invitations.update(decided)
            if accept:
                await self._grant(card, user_id, current.terms)
            await self._audit.record(
                f"project.invitation.{'accept' if accept else 'decline'}",
                actor_id=user_id,
                target=str(card.id),
                details={"invitation_id": invitation_id, "role": current.terms.role.value},
            )
            if current.invited_by is not None:
                kind = NotificationKind.invitation_accepted if accept else NotificationKind.invitation_declined
                await self._notifier.notify(
                    current.invited_by,
                    kind,
                    _payload(card, actor.name or await self._name(user_id), current, status.value),
                )
        view = await self._invitations.my_view(invitation_id)
        if view is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return view

    async def _claim(self, invitation: ProjectInvitation, user_id: str, *, by_token: bool) -> ProjectInvitation:
        """Чужое приглашение: 404 по id; по ссылке из письма 403 с подсказкой адреса (S11)."""
        if invitation.invitee_user_id == user_id:
            return invitation
        user = await self._users.get(user_id)
        email_matches = (
            user is not None
            and user.email_verified
            and invitation.invitee_email is not None
            and invitation.invitee_user_id is None
            and user.email_normalized == invitation.invitee_email
        )
        if email_matches:
            return invitation
        if by_token:
            hint = mask_email(invitation.invitee_email) or ""
            raise IdentityError(IdentityErrorCode.invitation_email_mismatch, extra={"email_hint": hint})
        raise IdentityError(IdentityErrorCode.not_found)

    async def _grant(self, card: ProjectCard, user_id: str, terms: MemberTerms) -> None:
        """Уже участник: роль повышается, если приглашённая старше, иначе остаётся прежней."""
        if user_id == card.owner_user_id:
            return
        existing = await self._member_roles.direct_user_role(card.id, user_id)
        if existing is not None and stronger(existing, terms.role) is existing:
            return
        await self._members.set_member(card.id, member_grant(user_id, terms))


class AcceptInvitationUC(_Decide):
    async def execute(self, actor: Actor, invitation_id: str) -> MyInvitationView:
        return await self._decide(actor, invitation_id, True, by_token=False)


class DeclineInvitationUC(_Decide):
    async def execute(self, actor: Actor, invitation_id: str) -> MyInvitationView:
        return await self._decide(actor, invitation_id, False, by_token=False)


class AcceptInvitationTokenUC(_Decide):
    async def execute(self, actor: Actor, token: str) -> MyInvitationView:
        invitation = await self._invitations.get_by_token_hash(hash_token(token))
        if invitation is None or invitation.status is InvitationStatus.revoked:
            raise IdentityError(IdentityErrorCode.not_found)
        return await self._decide(actor, invitation.id, True, by_token=True)


class PreviewInvitationTokenUC(_Base):
    """Что показать по ссылке из письма. Имя проекта только у действующего приглашения."""

    async def execute(self, token: str) -> InvitationPreview:
        invitation = await self._invitations.get_by_token_hash(hash_token(token)) if token else None
        if invitation is None or invitation.status is InvitationStatus.revoked:
            return InvitationPreview("invalid")
        status = invitation.effective_status(self._clock())
        if status is InvitationStatus.expired:
            return InvitationPreview("expired")
        if status is not InvitationStatus.pending:
            return InvitationPreview("used")
        card = await self._cards.card(invitation.project_id)
        if card is None:
            return InvitationPreview("invalid")
        needs_signup = invitation.registration_invite_id is not None and invitation.invitee_user_id is None
        return InvitationPreview(
            "ok",
            project_name=card.name,
            inviter_name=await self._name(invitation.invited_by),
            role=invitation.terms.role,
            email_hint=mask_email(invitation.invitee_email),
            registration_token=token if needs_signup else None,
        )
