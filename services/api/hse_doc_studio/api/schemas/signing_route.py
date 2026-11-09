"""Формы маршрута подписания (docs/design/signing-route.md, раздел 8): ход маршрута, правка, предпросмотр, отправка.

Строгие, как остальной контракт сервера: лишнее поле это ошибка, все поля ответа приходят явно, пустое значение
`null`. Повторяют zod-схемы `entities/signing-route` фронтенда (срез W1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from hse_doc_studio.api.schemas.common import StrictModel

SIGNING_TEXT_MAX = 2000
PASSPHRASE_MAX = 500
PERSONA_MAX = 64

SigningRouteStatusName = Literal["draft", "active", "paused", "returned", "completed", "cancelled", "archived"]
SigningRoutePhaseName = Literal["approval", "signing", "done"]
SigningStopReasonName = Literal["rebuilt", "marks_changed", "frozen_changed", "participant_left", "returned"]
ParticipantStateName = Literal["invited", "waiting", "to_approve", "to_approve_sign", "to_sign", "done", "returned"]
SigningNextActionName = Literal["wait", "approve", "approve_and_sign", "sign", "done"]
ParticipantMembershipName = Literal["member", "invited", "missing"]
RouteSignMethodName = Literal["image", "detached", "pades"]
RouteSlotStatusName = Literal["pending", "signed", "invalid", "stale"]
RouteEventKindName = Literal[
    "sent",
    "approved",
    "signed",
    "returned",
    "paused",
    "resumed",
    "cancelled",
    "completed",
    "reminded",
    "invited",
    "frozen",
]


class SigningProfileRef(StrictModel):
    id: str
    name: dict[str, str]


class SigningPersonRef(StrictModel):
    id: str
    name: str


class RouteSlotRef(StrictModel):
    doc_id: str = Field(min_length=1, max_length=128)
    slot_id: str = Field(min_length=1, max_length=128)


class RouteEvent(StrictModel):
    id: str
    kind: RouteEventKindName
    round: int = Field(ge=0)
    at: datetime
    who: str | None
    comment: str | None
    reason: SigningStopReasonName | None


class RouteParticipant(StrictModel):
    id: str
    persona: str
    user_id: str | None
    invitation_id: str | None
    name: str | None
    membership: ParticipantMembershipName
    assignments: list[RouteSlotRef]
    method: RouteSignMethodName | None
    state: ParticipantStateName
    next_action: SigningNextActionName
    approved_at: datetime | None
    notified_at: datetime | None
    reminded_at: datetime | None
    reminders: int = Field(ge=0)


class RouteDocSlot(StrictModel):
    slot_id: str
    label: dict[str, str]
    participant_id: str | None
    optional: bool
    status: RouteSlotStatusName


class RouteDoc(StrictModel):
    doc_id: str
    name: dict[str, str]
    frozen: bool
    slots: list[RouteDocSlot]


class SigningRouteResponse(StrictModel):
    """Ход маршрута глазами автора: ответ чтения и всех действий автора."""

    id: str
    project_id: str
    profile: SigningProfileRef
    status: SigningRouteStatusName
    phase: SigningRoutePhaseName | None
    round: int = Field(ge=0)
    current_step: int | None = Field(ge=1)
    deadline: datetime | None
    message: str | None
    stop_reason: SigningStopReasonName | None
    sent_by: SigningPersonRef | None
    sent_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    docs: list[RouteDoc]
    steps: list[list[RouteParticipant]]
    events: list[RouteEvent]


class SigningWaitingFor(StrictModel):
    name: str | None
    persona: str


class SigningRouteSummary(StrictModel):
    id: str
    profile: SigningProfileRef
    status: SigningRouteStatusName
    phase: SigningRoutePhaseName | None
    round: int = Field(ge=0)
    current_step: int | None = Field(ge=1)
    steps_total: int = Field(ge=0)
    deadline: datetime | None
    stop_reason: SigningStopReasonName | None
    sent_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    waiting_for: list[SigningWaitingFor]


class SigningRouteList(StrictModel):
    items: list[SigningRouteSummary]


class CreateSigningRouteRequest(StrictModel):
    profile_id: str = Field(min_length=1, max_length=128)


class RouteParticipantDraft(StrictModel):
    """Человек в шаге: участник маршрута (`id`) или новый (`null`); пары «документ, слот» назначает сервер."""

    id: str | None = None
    persona: str = Field(min_length=1, max_length=PERSONA_MAX)
    user_id: str | None = Field(default=None, max_length=64)
    invitation_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _one_person(self) -> RouteParticipantDraft:
        if self.user_id is not None and self.invitation_id is not None:
            raise ValueError("user_id and invitation_id are mutually exclusive")
        return self


class UpdateSigningRouteRequest(StrictModel):
    steps: list[list[RouteParticipantDraft]] = Field(max_length=32)
    extra_slots: list[RouteSlotRef] = Field(default_factory=list, max_length=64)
    deadline: datetime | None = None
    message: str | None = Field(default=None, max_length=SIGNING_TEXT_MAX)

    @model_validator(mode="after")
    def _steps_not_empty(self) -> UpdateSigningRouteRequest:
        if any(not step for step in self.steps):
            raise ValueError("a step must have at least one person")
        return self


class SigningKeyRequest(StrictModel):
    """Ключ Студии для подписи на сервере: выбранный или по умолчанию; пароль только на время подписи."""

    identity_id: str | None = None
    passphrase: str | None = Field(default=None, max_length=PASSPHRASE_MAX)


class SigningKeyInfo(StrictModel):
    id: str
    label: str
    kind: str
    protected: bool
    signer: str


class SigningRoutePreviewDoc(StrictModel):
    doc_id: str
    name: dict[str, str]
    built: bool
    token: str | None


class SigningRoutePreviewParticipant(StrictModel):
    participant_id: str
    step: int = Field(ge=1)
    persona: str
    name: str | None
    membership: ParticipantMembershipName
    method: RouteSignMethodName | None
    methods: list[RouteSignMethodName]
    chooses_method: bool
    image_ready: bool
    plate_ready: bool
    actions: int = Field(ge=0, le=2)


class SigningRouteBlocker(StrictModel):
    code: str
    doc_id: str | None
    slot_id: str | None
    participant_id: str | None


class SigningRoutePreview(StrictModel):
    route_id: str
    can_send: bool
    can_send_and_sign: bool
    visual_step: int = Field(ge=0)
    docs: list[SigningRoutePreviewDoc]
    participants: list[SigningRoutePreviewParticipant]
    blockers: list[SigningRouteBlocker]
    sender_key: SigningKeyInfo | None


class SendSigningRouteRequest(StrictModel):
    expected: dict[str, str]
    sign: SigningKeyRequest | None = None


class EmptyRequest(StrictModel):
    """Тело действий без параметров (`{}`): предпросмотр, отмена, снятие с контроля."""
