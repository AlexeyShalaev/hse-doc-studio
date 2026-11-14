"""Актуальность письма для повтора (docs/design/mail-log.md, 14.2, V5): по объекту строки журнала.

Одна-две выборки по первичному ключу на письмо: получатель, проект и объект из `ref`. Общие правила по самой
строке (итог, ссылка с токеном, окно, SMTP) проверяет `resend_block` в `core/mail/journal.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hse_doc_studio.core.mail.compose import MailTemplate
from hse_doc_studio.core.mail.journal import MailLogEntry, MailRefKind, ResendBlock, known_template
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.invitations import AccessRequestRow, ProjectInvitationRow, ProjectTransferRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.orm.signing_routes import SigningRouteParticipantRow, SigningRouteRow
from hse_doc_studio.infra.db.session import SessionProvider

_PENDING = "pending"
# Письма об аккаунте уходят и на неподтверждённый адрес (P5..P7), уведомления проектов только на подтверждённый.
_ACCOUNT_NOTICES = frozenset({MailTemplate.reset_notice, MailTemplate.passkey_added, MailTemplate.passkey_reset})
# Просьба подписать или согласовать: актуальна, пока маршрут идёт и получатель ещё не ответил в этом раунде.
_ASKING = frozenset(
    {
        MailTemplate.signing_request,
        MailTemplate.signing_request_sign,
        MailTemplate.signing_request_new_version,
        MailTemplate.signing_reminder,
    }
)
_ROUTE_CLOSED = frozenset({"cancelled", "archived"})
# Сообщение о состоянии маршрута актуально, пока маршрут в этом состоянии.
_ROUTE_STATUS_FOR = {MailTemplate.signing_returned: "returned", MailTemplate.signing_completed: "completed"}
# Объекты, письмо о которых актуально, пока они ждут ответа (`pending`, у приглашения ещё и срок).
_PENDING_OBJECTS: dict[str, tuple[type[ProjectInvitationRow | AccessRequestRow | ProjectTransferRow], ResendBlock]] = {
    MailRefKind.project_invitation.value: (ProjectInvitationRow, ResendBlock.invitation_done),
    MailRefKind.access_request.value: (AccessRequestRow, ResendBlock.request_done),
    MailRefKind.transfer.value: (ProjectTransferRow, ResendBlock.transfer_done),
}


def _uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _answered(participant: SigningRouteParticipantRow, route_round: int) -> bool:
    approval: Any = participant.approval
    answered = isinstance(approval, dict) and approval.get("round") == route_round
    return answered or participant.skipped is not None


class SqlMailRelevance:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def check(self, entry: MailLogEntry) -> ResendBlock | None:
        template = known_template(entry.template)
        if template is None:
            return ResendBlock.template_gone
        async with self._sessions.use() as db:
            return (
                await self._recipient(db, entry, template)
                or await self._project(db, entry)
                or await self._object(db, entry, template)
            )

    async def _recipient(self, db: AsyncSession, entry: MailLogEntry, template: MailTemplate) -> ResendBlock | None:
        if not entry.to_user_id:
            return None
        user = await db.get(UserRow, entry.to_user_id)
        if user is None:
            return ResendBlock.recipient_gone
        if user.email.strip().lower() != entry.to_email.strip().lower():
            return ResendBlock.recipient_changed
        verified = user.email_verified or template in _ACCOUNT_NOTICES
        if user.status != "active" or not verified:
            return ResendBlock.recipient_blocked
        return None

    async def _project(self, db: AsyncSession, entry: MailLogEntry) -> ResendBlock | None:
        project_id = _uuid(entry.project_id)
        if project_id is None:
            return None
        project = await db.get(ProjectRow, project_id)
        return ResendBlock.project_gone if project is None or project.deleted_at is not None else None

    async def _object(self, db: AsyncSession, entry: MailLogEntry, template: MailTemplate) -> ResendBlock | None:
        kind, ref_id = entry.ref_kind, entry.ref_id
        if not kind or not ref_id:
            return None
        if kind == MailRefKind.signing_route.value:
            return await self._route(db, entry, template, ref_id)
        spec = _PENDING_OBJECTS.get(kind)
        if spec is None:
            return None
        row_type, done = spec
        row: ProjectInvitationRow | AccessRequestRow | ProjectTransferRow | None = await db.get(row_type, ref_id)
        if row is None:
            return ResendBlock.object_gone
        expires = getattr(row, "expires_at", None)
        live = row.status == _PENDING and (expires is None or expires > datetime.now(UTC))
        return None if live else done

    async def _route(
        self, db: AsyncSession, entry: MailLogEntry, template: MailTemplate, ref_id: str
    ) -> ResendBlock | None:
        route_id = _uuid(ref_id)
        route = await db.get(SigningRouteRow, route_id) if route_id is not None else None
        if route is None:
            return ResendBlock.object_gone
        wanted = _ROUTE_STATUS_FOR.get(template)
        if wanted is not None:
            return None if route.status == wanted else ResendBlock.route_done
        if template not in _ASKING:
            return ResendBlock.route_done if route.status in _ROUTE_CLOSED else None
        if route.status != "active":
            return ResendBlock.route_done
        return await self._waiting(db, entry, route)

    async def _waiting(self, db: AsyncSession, entry: MailLogEntry, route: SigningRouteRow) -> ResendBlock | None:
        """Получатель ещё участник идущего маршрута и не ответил в этом раунде."""
        if not entry.to_user_id:
            return None
        rows = await db.execute(
            select(SigningRouteParticipantRow).where(
                SigningRouteParticipantRow.route_id == route.id,
                SigningRouteParticipantRow.user_id == entry.to_user_id,
            )
        )
        waiting = [p for p in rows.scalars() if not _answered(p, route.round)]
        return None if waiting else ResendBlock.route_done
