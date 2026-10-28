"""Приглашения администратора: создать, посмотреть, отозвать. Принимаются при регистрации (`RegisterUC`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import MailKind, RegistrationInvite
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import hash_token, is_valid_email, new_token, normalize_email
from hse_doc_studio.core.identity.protocols import IAuditLog, IRegistrationInviteRepository, IUserRepository
from hse_doc_studio.core.identity.registration import invite_usable
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.use_cases.identity.mail import LinkDelivery, auth_link

INVITE_PATH = "/invite"
DEFAULT_INVITE_TTL = timedelta(days=7)
MAX_INVITE_TTL = timedelta(days=30)


@dataclass(frozen=True)
class CreatedInvite:
    invite: RegistrationInvite
    # Секрет приглашения: виден только здесь, в БД лежит хеш.
    token: str
    # Ссылка для пересылки; None, если письмо ушло по почте.
    link: str | None


@dataclass(frozen=True)
class InvitationInfo:
    email: str | None
    invited_by: str
    org_id: str | None


def _require_admin(actor: Actor) -> str:
    # Приглашать от имени организации смогут и её админы, когда появятся организации.
    if not actor.is_instance_admin or actor.id is None:
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor.id


class CreateInviteUC:
    def __init__(
        self,
        invites: IRegistrationInviteRepository,
        delivery: LinkDelivery,
        audit: IAuditLog,
        *,
        public_url: str | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._invites = invites
        self._delivery = delivery
        self._audit = audit
        self._public_url = public_url
        self._clock = clock

    async def execute(
        self,
        actor: Actor,
        *,
        email: str | None = None,
        org_id: str | None = None,
        org_role: str | None = None,
        ttl: timedelta = DEFAULT_INVITE_TTL,
    ) -> CreatedInvite:
        creator = _require_admin(actor)
        if email is not None and not is_valid_email(email):
            raise IdentityError(IdentityErrorCode.invitation_invalid)
        if (org_role is not None) != (org_id is not None) or not timedelta(0) < ttl <= MAX_INVITE_TTL:
            raise IdentityError(IdentityErrorCode.invitation_invalid)
        now = self._clock()
        token = new_token()
        invite = RegistrationInvite(
            token_hash=hash_token(token),
            email=normalize_email(email) if email else None,
            created_by=creator,
            expires_at=now + ttl,
            id=hash_token(token)[:32],
            org_id=org_id,
            org_role=org_role,
        )
        await self._invites.add(invite)
        link = auth_link(self._public_url, INVITE_PATH, token)
        # Приглашение на адрес уходит письмом; без SMTP и для приглашения «на любого» ссылку пересылает сам админ.
        shown = await self._delivery.deliver(MailKind.invite, invite.email, link, now) if invite.email else link
        await self._audit.record(
            "invite.create", actor_id=creator, target=invite.id, details={"email": invite.email, "org_id": org_id}
        )
        return CreatedInvite(invite=invite, token=token, link=shown)


class ListInvitesUC:
    def __init__(self, invites: IRegistrationInviteRepository) -> None:
        self._invites = invites

    async def execute(self, actor: Actor) -> list[RegistrationInvite]:
        _require_admin(actor)
        return await self._invites.list()


class RevokeInviteUC:
    def __init__(self, invites: IRegistrationInviteRepository, audit: IAuditLog) -> None:
        self._invites = invites
        self._audit = audit

    async def execute(self, actor: Actor, invite_id: str) -> None:
        creator = _require_admin(actor)
        if not await self._invites.revoke(invite_id):
            raise IdentityError(IdentityErrorCode.invitation_invalid)
        await self._audit.record("invite.revoke", actor_id=creator, target=invite_id)


class InvitationInfoUC:
    """Что показать на форме регистрации по ссылке: адрес, кто пригласил. Для негодного токена один ответ."""

    def __init__(self, invites: IRegistrationInviteRepository, users: IUserRepository, clock: Clock = utc_now) -> None:
        self._invites = invites
        self._users = users
        self._clock = clock

    async def execute(self, token: str) -> InvitationInfo:
        invite = await self._invites.get(hash_token(token))
        if invite is None or not invite_usable(invite, invite.email or "", self._clock()):
            raise IdentityError(IdentityErrorCode.invitation_invalid)
        inviter = await self._users.get(invite.created_by)
        return InvitationInfo(email=invite.email, invited_by=inviter.name if inviter else "", org_id=invite.org_id)
