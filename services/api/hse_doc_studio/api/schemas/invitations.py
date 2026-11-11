"""Формы трека invites: приглашения, запросы доступа, передача владения, уведомления (эталоны contracts/server)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.invitations.policy import NEXT_PATH_MAX, safe_next_path

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
    "review_thread",
    "review_reply",
    "review_mention",
    "review_resolved",
    "backup_failed",
    "system_alert",
    "signing_request",
    "signing_reminder",
    "signing_returned",
    "signing_paused",
    "signing_completed",
    "signing_cancelled",
    "signing_new_version",
    "runner_disk_cleaned",
]
NotificationOutcome = Literal[
    "accepted",
    "declined",
    "approved",
    "denied",
    "resolved",
    "reopened",
    "storage_warning",
    "storage_critical",
    "diag_fail",
    "diag_warn",
    "diag_recovered",
    # Маршрут подписания: ход запроса (`signing_request`, `signing_reminder`) и причина остановки (`signing_paused`).
    "approve",
    "approve_sign",
    "sign",
    "rebuilt",
    "sent_changed",
    "marks_changed",
    "frozen_changed",
    "participant_left",
    # Очистка диска личного раннера (`runner_disk_cleaned`): итог команды.
    "done",
    "cancelled",
    "error",
    "lost",
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
    # Куда вести после принятия: относительный путь сайта (`/sign/<проект>/<маршрут>` из редактора маршрута).
    next: str | None = Field(default=None, max_length=NEXT_PATH_MAX)

    @model_validator(mode="after")
    def _one_invitee(self) -> CreateProjectInvitationRequest:
        if (self.user_id is None) == (self.email is None):
            raise ValueError("нужно ровно одно из user_id и email")
        if self.next is not None and safe_next_path(self.next) is None:
            raise ValueError("next: только относительный путь этого сайта")
        return self


class InvitationDraftRequest(StrictModel):
    """Для чего нужен готовый текст: тот же выбор, что в форме приглашения; адресат может быть ещё не введён."""

    user_id: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=EMAIL_MAX)
    role: GrantRoleName
    persona: str | None = Field(default=None, max_length=PERSONA_MAX)


class InvitationDraft(StrictModel):
    message: str


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
    # Сообщение приглашающего, как в письме; только у действующего приглашения.
    message: str | None


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
    outcome: NotificationOutcome | None
    path: str | None = None
    excerpt: str | None = None
    # Маршрут подписания: точка сдачи и срок маршрута.
    profile_id: str | None = None
    deadline: datetime | None = None
    # Запрос раунда новой версии (12.6): «{автор} просит подписать новую версию»; у остальных false.
    new_version: bool = False
    # Очистка диска личного раннера (`runner_disk_cleaned`): освобождено байт; у остальных видов null.
    freed_bytes: int | None = None


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
    # Задачи «На подпись» (GET /account/signing-tasks): где сейчас нужно действие человека.
    signing_tasks: int


class InboxBadge(StrictModel):
    """Счётчик для шапки в bootstrap вошедшего: непрочитанные уведомления плюс ожидающие решения."""

    unread: int
