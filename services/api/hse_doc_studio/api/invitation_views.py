"""Перевод значений трека invites в формы ответа (api/schemas/invitations.py)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, cast

from fastapi import Request

from hse_doc_studio.api.schemas import invitations as s
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.invitations.entities import (
    AccessRequestView,
    InvitationView,
    MyAccessRequestView,
    MyInvitationView,
    Notification,
    TransferStatus,
    TransferView,
)

_log = logging.getLogger(__name__)


def require_user() -> Actor:
    actor = current_actor()
    if actor is None or actor.id is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


def grant_role(role: Role) -> s.GrantRoleName:
    return cast(s.GrantRoleName, role.value)


def invitation(view: InvitationView, now: datetime) -> s.ProjectInvitation:
    inv = view.invitation
    if inv.invitee_email is not None:
        # Пригласившему видна введённая им почта; был ли аккаунт, ответ не говорит (T11).
        invitee = s.InvitationInvitee(kind="email", user_id=None, name=None, email_hint=inv.invitee_email)
    else:
        invitee = s.InvitationInvitee(kind="user", user_id=inv.invitee_user_id, name=view.invitee_name, email_hint=None)
    return s.ProjectInvitation(
        id=inv.id,
        invitee=invitee,
        role=grant_role(inv.terms.role),
        persona=inv.terms.persona,
        can_share=inv.terms.can_share,
        show_sources=inv.terms.show_sources,
        can_edit_all=inv.terms.can_edit_all,
        message=inv.message,
        invited_by=s.PersonRef(id=inv.invited_by, name=view.inviter_name or "") if inv.invited_by else None,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        status=inv.effective_status(now).value,
        sent_count=inv.sent_count,
        last_sent_at=inv.last_sent_at,
    )


def my_invitation(view: MyInvitationView, now: datetime) -> s.MyInvitation:
    inv = view.invitation
    return s.MyInvitation(
        id=inv.id,
        project=s.InvitationProject(id=str(inv.project_id), name=view.project_name, owner_name=view.owner_name),
        role=grant_role(inv.terms.role),
        persona=inv.terms.persona,
        message=inv.message,
        invited_by=s.PersonRef(id=inv.invited_by, name=view.inviter_name or "") if inv.invited_by else None,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        status=inv.effective_status(now).value,
    )


def access_request(view: AccessRequestView) -> s.AccessRequestView:
    req = view.request
    return s.AccessRequestView(
        id=req.id,
        requester=s.AccessRequester(id=req.user_id, name=view.name, email=view.email),
        message=req.message,
        status=req.status.value,
        created_at=req.created_at,
        decided_at=req.decided_at,
        decided_by=s.PersonRef(id=req.decided_by, name=view.decided_by_name or "") if req.decided_by else None,
        granted_role=grant_role(req.granted_role) if req.granted_role else None,
    )


def my_access_request(view: MyAccessRequestView) -> s.MyAccessRequest:
    req = view.request
    return s.MyAccessRequest(
        id=req.id,
        project=s.MyAccessRequestProject(id=str(req.project_id), name=view.project_name),
        status=req.status.value,
        created_at=req.created_at,
        decided_at=req.decided_at,
        granted_role=grant_role(req.granted_role) if req.granted_role else None,
    )


def transfer_info(view: TransferView) -> s.ProjectTransferInfo:
    t = view.transfer
    return s.ProjectTransferInfo(
        id=t.id,
        to=s.TransferParty(kind=t.to_kind, id=t.to_id, name=view.to_name),
        created_at=t.created_at,
        expires_at=t.expires_at,
        message=t.message,
    )


def my_transfer(view: TransferView, now: datetime) -> s.MyTransfer:
    t = view.transfer
    status: s.TransferStatusName | Literal["expired"] = (
        "expired" if t.status is TransferStatus.pending and t.expires_at <= now else t.status.value
    )
    return s.MyTransfer.model_validate(
        {
            "id": t.id,
            "project": {"id": str(t.project_id), "name": view.project_name},
            "from": {"kind": t.from_kind, "name": view.from_name},
            "message": t.message,
            "created_at": t.created_at,
            "expires_at": t.expires_at,
            "status": status,
            "previous_owner_role": "editor" if t.from_kind == "user" else None,
        }
    )


def notification(item: Notification) -> s.NotificationModel:
    p = item.payload
    outcome = p.outcome if p.outcome in ("accepted", "declined", "approved", "denied") else None
    return s.NotificationModel(
        id=item.id,
        kind=item.kind.value,
        created_at=item.created_at,
        read_at=item.read_at,
        payload=s.NotificationPayloadModel(
            project_id=p.project_id,
            project_name=p.project_name,
            actor_name=p.actor_name,
            role=p.role,
            ref_id=p.ref_id,
            outcome=cast(Literal["accepted", "declined", "approved", "denied"] | None, outcome),
        ),
    )


async def inbox_badge(request: Request, user_id: str | None) -> s.InboxBadge | None:
    """Счётчик колокольчика для bootstrap; сбой подсчёта bootstrap не ломает (счётчик подтянет опрос)."""
    if user_id is None:
        return None
    from hse_doc_studio.use_cases.notifications.inbox import InboxSummaryUC  # noqa: PLC0415

    try:
        uc = await request.state.dishka_container.get(InboxSummaryUC)
        return s.InboxBadge(unread=await uc.badge(user_id))
    except Exception:
        _log.warning("inbox badge unavailable", exc_info=True)
        return None
