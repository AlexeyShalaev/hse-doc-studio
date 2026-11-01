"""Повторная отправка приглашения: старая ссылка гаснет, выдаётся новая с теми же адресом и членством."""

from __future__ import annotations

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IRegistrationInviteRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.invites import CreatedInvite, CreateInviteUC


class ResendInviteUC:
    def __init__(
        self,
        invites: IRegistrationInviteRepository,
        create: CreateInviteUC,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._invites = invites
        self._create = create
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, actor: Actor, invite_id: str) -> CreatedInvite:
        """Принятое приглашение не повторить, просроченное можно. Секрет хранится хешем, поэтому ссылка новая."""
        admin_id = require_admin(actor)
        old = await self._invites.get_by_id(invite_id)
        if old is None or old.used_at is not None:
            raise IdentityError(IdentityErrorCode.not_found)
        async with self._uow.begin():
            await self._invites.revoke(old.id)
            created = await self._create.execute(actor, email=old.email, org_id=old.org_id, org_role=old.org_role)
            await self._audit.record(
                "admin.invite_resent", actor_id=admin_id, target=created.invite.id, details={"previous": old.id}
            )
        return created
