"""Формы трека invites: приглашения, запросы доступа, передача владения, уведомления (эталоны contracts/server)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from hse_doc_studio.api.schemas.common import StrictModel

GrantRoleName = Literal["reader", "reviewer", "editor"]
InvitationStatusName = Literal["pending", "accepted", "declined", "revoked", "expired"]
AccessRequestStatusName = Literal["pending", "approved", "denied", "cancelled"]
TransferStatusName = Literal["pending", "accepted", "declined", "cancelled", "superseded"]
NotificationKindName = Literal[
    "project_invitation",
    "invitation_accepted",
    "invitation_declined",
    "access_request",
    "access_request_decided",
    "transfer_request",
    "transfer_decided",
    "member_removed",
]
OwnerKindName = Literal["user", "org"]
MESSAGE_MAX = 1000
PERSONA_MAX = 64
EMAIL_MAX = 320


class PersonRef(StrictModel):
    id: str
    name: str


class InvitationInvitee(StrictModel):
    kind: Literal["user", "email"]
    user_id: str | None
    name: str | None
    # У почтового приглашения пригласившему видна полная почта, у приглашения человеку только маска.
    email_hint: str | None


class ProjectInvitation(StrictModel):
    id: str
    invitee: InvitationInvitee
    role: GrantRoleName
    persona: str | None
    can_share: bool
    show_sources: bool
    can_edit_all: bool
    message: str | None
    invited_by: PersonRef | None
    created_at: datetime
    expires_at: datetime
    status: InvitationStatusName
    sent_count: int
    last_sent_at: datetime


class ProjectInvitationPage(StrictModel):
    items: list[ProjectInvitation]
    total: int
    limit: int
    offset: int


class CreateProjectInvitationRequest(StrictModel):
    user_id: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=EMAIL_MAX)
    role: GrantRoleName
    persona: str | None = Field(default=None, max_length=PERSONA_MAX)
    can_share: bool = False
    show_sources: bool = True
    can_edit_all: bool = False
    message: str | None = Field(default=None, max_length=MESSAGE_MAX)
    expires_in_days: int = Field(default=7, ge=1, le=30)

    @model_validator(mode="after")
    def _one_invitee(self) -> CreateProjectInvitationRequest:
        if (self.user_id is None) == (self.email is None):
            raise ValueError("нужно ровно одно из user_id и email")
        return self


class ProjectInvitationCreated(StrictModel):
    invitation: ProjectInvitation
    delivery: Literal["email", "manual", "inbox"]
    # Ссылка для пересылки вручную: только когда почта не настроена и адресата пока нет.
    link: str | None


class InvitationProject(StrictModel):
    id: str
    name: str
    owner_name: str


class MyInvitation(StrictModel):
    id: str
    project: InvitationProject
    role: GrantRoleName
    persona: str | None
    message: str | None
    invited_by: PersonRef | None
    created_at: datetime
    expires_at: datetime
    status: InvitationStatusName


class MyInvitationList(StrictModel):
    items: list[MyInvitation]


class ProjectInvitationPreview(StrictModel):
    state: Literal["ok", "expired", "used", "invalid"]
    project_name: str | None
    inviter_name: str | None
    role: GrantRoleName | None
    email_hint: str | None
    # S12: регистрационное приглашение для адреса без аккаунта в режиме «только по приглашению».
    registration_token: str | None


class AccessRequester(StrictModel):
    id: str
    name: str
    email: str


class AccessRequestView(StrictModel):
    id: str
    requester: AccessRequester
    message: str | None
    status: AccessRequestStatusName
    created_at: datetime
    decided_at: datetime | None
    decided_by: PersonRef | None
    granted_role: GrantRoleName | None


class AccessRequestPage(StrictModel):
    items: list[AccessRequestView]
    total: int
    limit: int
    offset: int


class ApproveAccessRequest(StrictModel):
    role: GrantRoleName
    persona: str | None = Field(default=None, max_length=PERSONA_MAX)
    can_share: bool = False
    show_sources: bool = True
    can_edit_all: bool = False


class DenyAccessRequest(StrictModel):
    message: str | None = Field(default=None, max_length=MESSAGE_MAX)


class CreateAccessRequest(StrictModel):
    # Поле называется `project` внутри модели: проект запрашивающему не открыт, и гард маршрутов
    # проекта к нему не применяется (маршрут в таблице областей как `authenticated`).
    model_config = ConfigDict(extra="forbid", serialize_by_alias=True, validate_by_name=False)

    project: UUID = Field(alias="project_id")
    message: str | None = Field(default=None, max_length=MESSAGE_MAX)


class AccessRequestAccepted(StrictModel):
    accepted: Literal[True] = True


class MyAccessRequestProject(StrictModel):
    id: str
    # Имя видно только у одобренного запроса (S13).
    name: str | None


class MyAccessRequest(StrictModel):
    id: str
    project: MyAccessRequestProject
    status: AccessRequestStatusName
    created_at: datetime
    decided_at: datetime | None
    granted_role: GrantRoleName | None


class MyAccessRequestList(StrictModel):
    items: list[MyAccessRequest]


class TransferParty(StrictModel):
    kind: OwnerKindName
    id: str
    name: str


class ProjectTransferInfo(StrictModel):
    id: str
    to: TransferParty
    created_at: datetime
    expires_at: datetime
    message: str | None


class ProjectTransferState(StrictModel):
    pending: bool
    # Детали видит только тот, кто вправе передать проект; остальным только признак.
    transfer: ProjectTransferInfo | None


class StartProjectTransferRequest(StrictModel):
    to_kind: OwnerKindName
    # У организации это её адрес (slug), как в `transfer-candidates`.
    to_id: str = Field(min_length=1, max_length=64)
    message: str | None = Field(default=None, max_length=MESSAGE_MAX)
    confirm_name: str | None = Field(default=None, max_length=512)


class TransferProject(StrictModel):
    id: str
    name: str


class TransferFrom(StrictModel):
    kind: OwnerKindName
    name: str


class MyTransfer(StrictModel):
    id: str
    project: TransferProject
    from_: TransferFrom = Field(alias="from")
    message: str | None
    created_at: datetime
    expires_at: datetime
    status: TransferStatusName | Literal["expired"]
    # Роль, которую получит нынешний владелец-человек; null у передачи от организации.
    previous_owner_role: GrantRoleName | None

    model_config = ConfigDict(extra="forbid", serialize_by_alias=True, validate_by_name=False)


class MyTransferList(StrictModel):
    items: list[MyTransfer]


class NotificationPayloadModel(StrictModel):
    project_id: str | None
    project_name: str | None
    actor_name: str | None
    role: str | None
    ref_id: str | None
    outcome: Literal["accepted", "declined", "approved", "denied"] | None


class NotificationModel(StrictModel):
    id: str
    kind: NotificationKindName
    created_at: datetime
    read_at: datetime | None
    payload: NotificationPayloadModel


class NotificationPage(StrictModel):
    items: list[NotificationModel]
    total: int
    limit: int
    offset: int


class MarkNotificationsReadRequest(StrictModel):
    # null значит «все непрочитанные».
    ids: list[str] | None = Field(default=None, max_length=200)


class InboxSummary(StrictModel):
    unread: int
    invitations: int
    transfers: int
    access_requests: int


class InboxBadge(StrictModel):
    """Счётчик для шапки в bootstrap вошедшего: непрочитанные уведомления плюс ожидающие решения."""

    unread: int
