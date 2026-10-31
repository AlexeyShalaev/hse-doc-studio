"""Приглашения в проект, запросы доступа, передачи владения и уведомления: значения без HTTP и SQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from hse_doc_studio.core.access.entities import Role

INVITATION_TOKEN_PREFIX = "hspi_"  # noqa: S105 — префикс, не секрет
DEFAULT_INVITATION_DAYS = 7
MIN_INVITATION_DAYS = 1
MAX_INVITATION_DAYS = 30
MAX_PENDING_INVITATIONS = 50
# Повторная отправка: не чаще раза в 10 минут и не больше 5 раз сверх первой.
RESEND_INTERVAL = timedelta(minutes=10)
MAX_RESENDS = 5
MESSAGE_MAX = 1000
TRANSFER_TTL = timedelta(days=7)
# После отказа повторный запрос доступа к тому же проекту не раньше чем через 7 дней.
ACCESS_REQUEST_COOLDOWN = timedelta(days=7)
NOTIFICATION_RETENTION = timedelta(days=90)

GRANTABLE_ROLES = (Role.reader, Role.reviewer, Role.editor)
ROLE_RANK = {Role.reader: 0, Role.reviewer: 1, Role.editor: 2, Role.owner: 3}
SUPERVISOR_PERSONAS = frozenset({"supervisor", "co_supervisor", "academic_supervisor"})


class InvitationStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    revoked = "revoked"
    # Не хранится: `pending` с истёкшим сроком.
    expired = "expired"


class AccessRequestStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    cancelled = "cancelled"


class TransferStatus(StrEnum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    cancelled = "cancelled"
    superseded = "superseded"


class NotificationKind(StrEnum):
    project_invitation = "project_invitation"
    invitation_accepted = "invitation_accepted"
    invitation_declined = "invitation_declined"
    access_request = "access_request"
    access_request_decided = "access_request_decided"
    transfer_request = "transfer_request"
    transfer_decided = "transfer_decided"
    member_removed = "member_removed"


# Письмо уходит только для этих видов (S15), и только если SMTP настроен.
MAILED_KINDS = frozenset(
    {NotificationKind.project_invitation, NotificationKind.access_request, NotificationKind.transfer_request}
)

InvitationDelivery = Literal["email", "manual", "inbox"]
OwnerKind = Literal["user", "org"]


@dataclass(frozen=True)
class NotificationPayload:
    """Одна форма для всех видов: id и подписи на момент события, без секретов."""

    project_id: str | None = None
    project_name: str | None = None
    actor_name: str | None = None
    role: str | None = None
    ref_id: str | None = None
    outcome: str | None = None


@dataclass(frozen=True)
class Notification:
    id: str
    user_id: str
    kind: NotificationKind
    payload: NotificationPayload
    created_at: datetime
    read_at: datetime | None = None


@dataclass(frozen=True)
class MemberTerms:
    """Что получит участник: роль, персона и флаги, как у записи `project_members`."""

    role: Role
    persona: str | None = None
    can_share: bool = False
    show_sources: bool = True
    can_edit_all: bool = False


@dataclass(frozen=True)
class ProjectInvitation:
    id: str
    project_id: UUID
    invitee_user_id: str | None
    invitee_email: str | None
    terms: MemberTerms
    message: str | None
    token_hash: str | None
    invited_by: str | None
    created_at: datetime
    expires_at: datetime
    status: InvitationStatus
    last_sent_at: datetime
    sent_count: int = 1
    decided_at: datetime | None = None
    registration_invite_id: str | None = None

    def effective_status(self, now: datetime) -> InvitationStatus:
        if self.status is InvitationStatus.pending and self.expires_at <= now:
            return InvitationStatus.expired
        return self.status


@dataclass(frozen=True)
class InvitationView:
    """Строка «Ожидают» в проекте: приглашение и имена на сейчас."""

    invitation: ProjectInvitation
    invitee_name: str | None
    inviter_name: str | None


@dataclass(frozen=True)
class MyInvitationView:
    """Приглашение глазами адресата: проект, его владелец и кто пригласил."""

    invitation: ProjectInvitation
    project_name: str
    owner_name: str
    inviter_name: str | None


@dataclass(frozen=True)
class AccessRequest:
    id: str
    project_id: UUID
    user_id: str
    message: str | None
    status: AccessRequestStatus
    created_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    granted_role: Role | None = None


@dataclass(frozen=True)
class AccessRequestView:
    request: AccessRequest
    name: str
    email: str
    decided_by_name: str | None = None


@dataclass(frozen=True)
class MyAccessRequestView:
    request: AccessRequest
    # Имя проекта видно только у одобренного запроса (S13).
    project_name: str | None


@dataclass(frozen=True)
class ProjectTransfer:
    id: str
    project_id: UUID
    from_kind: OwnerKind
    from_id: str
    to_kind: OwnerKind
    to_id: str
    initiated_by: str | None
    message: str | None
    status: TransferStatus
    created_at: datetime
    expires_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None

    def expired(self, now: datetime) -> bool:
        return self.status is TransferStatus.pending and self.expires_at <= now


@dataclass(frozen=True)
class TransferView:
    transfer: ProjectTransfer
    project_name: str
    from_name: str
    to_name: str


@dataclass(frozen=True)
class ProjectCard:
    """Проект для приглашений и передачи: имя, владелец и подпись владельца на сейчас."""

    id: UUID
    name: str
    owner_user_id: str | None
    owner_org_id: str | None
    owner_name: str
    nda: bool = False

    @property
    def owner_kind(self) -> OwnerKind:
        return "org" if self.owner_org_id is not None else "user"

    @property
    def owner_id(self) -> str:
        return self.owner_org_id if self.owner_org_id is not None else self.owner_user_id or ""


@dataclass(frozen=True)
class InboxSummary:
    unread: int
    invitations: int
    transfers: int
    access_requests: int


def mask_email(email: str | None) -> str | None:
    """`petr@hse.ru` → `p***@hse.ru`: подсказка адреса без раскрытия его целиком."""
    if not email:
        return None
    local, sep, domain = email.partition("@")
    if not sep:
        return "***"
    return f"{local[:1]}***@{domain}"


def role_at_most(role: Role, ceiling: Role) -> bool:
    return ROLE_RANK[role] <= ROLE_RANK[ceiling]


def stronger(a: Role, b: Role) -> Role:
    return a if ROLE_RANK[a] >= ROLE_RANK[b] else b
