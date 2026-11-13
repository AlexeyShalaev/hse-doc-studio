"""Формы маршрута подписания (docs/design/signing-route.md, раздел 8): ход маршрута, правка, предпросмотр, отправка
и задача подписанта с её действиями.

Строгие, как остальной контракт сервера: лишнее поле это ошибка, все поля ответа приходят явно, пустое значение
`null`. Повторяют zod-схемы `entities/signing-route` фронтенда (срез W1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from hse_doc_studio.api.schemas.common import StrictModel

SIGNING_TEXT_MAX = 2000
PASSPHRASE_MAX = 500
PERSONA_MAX = 64

SigningRouteStatusName = Literal["draft", "active", "paused", "returned", "completed", "cancelled", "archived"]
SigningRoutePhaseName = Literal["approval", "signing", "done"]
SigningStopReasonName = Literal[
    "rebuilt", "sent_changed", "marks_changed", "frozen_changed", "participant_left", "returned"
]
# `skipped`: автор пропустил участника (signing-route.md, 13.3).
ParticipantStateName = Literal[
    "invited", "waiting", "to_approve", "to_approve_sign", "to_sign", "done", "returned", "skipped"
]
SigningNextActionName = Literal["wait", "approve", "approve_and_sign", "sign", "done"]
ParticipantMembershipName = Literal["member", "invited", "missing"]
RouteSignMethodName = Literal["image", "detached", "pades"]
# `skipped`: подпись пропущена маршрутом (signing-route.md, 13.3); статус слота плана подписей.
RouteSlotStatusName = Literal["pending", "signed", "invalid", "stale", "skipped"]
RouteVisibleMarkName = Literal["png", "plate", "none"]
SigningPlateKindName = Literal["x509", "openpgp", "manual"]
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
    "skipped",
    "marks_edited",
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
    # Участник маршрута, к которому относится событие (согласие, подпись, возврат); null у событий автора и сервера.
    participant_id: str | None
    comment: str | None
    reason: SigningStopReasonName | None
    # Только у `sent` новой версии (12.6): документы, у которых сменилась версия на подписи; иначе null.
    changed_docs: list[str] | None


SkipBlockerName = Literal["not_turn", "required_slots", "no_slots", "done"]


class RouteSkip(StrictModel):
    """Пропуск участника (13.6): `blocker` одна причина по старшинству `done`, `no_slots`, `not_turn`,
    `required_slots`; `keeps_marks` документы, где метка останется в зафиксированном PDF с ЭП, `refreezes` документы,
    которые маршрут зафиксирует заново без метки."""

    available: bool
    blocker: SkipBlockerName | None
    keeps_marks: list[str]
    refreezes: list[str]


class RouteParticipant(StrictModel):
    id: str
    persona: str
    user_id: str | None
    invitation_id: str | None
    name: str | None
    membership: ParticipantMembershipName
    # Имя персоны по карточке проекта: у приглашённого `name` только маска почты.
    card_name: str | None
    assignments: list[RouteSlotRef]
    method: RouteSignMethodName | None
    state: ParticipantStateName
    next_action: SigningNextActionName
    # Его согласие ещё меняет видимый слой: пока таких не осталось, PDF не фиксируется и ЭП не запрашивается.
    changes_visible: bool
    approved_at: datetime | None
    notified_at: datetime | None
    reminded_at: datetime | None
    reminders: int = Field(ge=0)
    # Когда пропущен в этом раунде (13.3); null, если не пропущен.
    skipped_at: datetime | None
    # Можно ли пропустить (13.6): только тому, кто управляет маршрутом, и только у идущего маршрута, иначе null.
    skip: RouteSkip | None


class RouteDocSlot(StrictModel):
    slot_id: str
    label: dict[str, str]
    participant_id: str | None
    # Слот добавлен к маршруту сверх точки: точка его не требует, автор включил сам (6.5).
    extra: bool
    # Подпись необязательна на точке маршрута: автора можно пропустить (13.3).
    optional: bool
    status: RouteSlotStatusName
    # Кто добавил слот сверх точки (15.11): `pack` шаблон, `author` автор; null у пары точки.
    added_by: Literal["pack", "author"] | None
    # Пресет точки отмечает подпись необязательной (15.11): галочка «по шаблону», если `optional` совпадает.
    preset_optional: bool


PresetPersonName = Literal["supervisor", "co_supervisor", "academic_supervisor"]
PresetRoleName = Literal["university", "company"]
PresetDiffName = Literal["order", "slots", "optional"]


class RoutePresetCondition(StrictModel):
    """Условие слота сверх точки (`when`, 15.3): человек проекта указан, а с `role` указан и с такой ролью."""

    person: PresetPersonName
    role: PresetRoleName | None


class RoutePresetSlot(StrictModel):
    doc_id: str
    slot_id: str
    when: RoutePresetCondition | None


class RoutePresetSkipped(StrictModel):
    """Слот сверх точки, который шаблон не добавил: условие на людях проекта не выполнено."""

    doc_id: str
    slot_id: str
    when: RoutePresetCondition


class RoutePreset(StrictModel):
    """Пресет точки для проекта сейчас (15.11): шаги, слоты сверх точки, отметки и чем маршрут отличается."""

    version: str
    # Шаги пресета персонами, внутри шага параллельно.
    steps: list[list[str]]
    extra_slots: list[RoutePresetSlot]
    optional: list[RouteSlotRef]
    skipped_by_condition: list[RoutePresetSkipped]
    # Пусто: маршрут как в шаблоне.
    differs: list[PresetDiffName]


class RouteDocVersion(StrictModel):
    """Версия на подписи документа (12.3): sha256 копии, когда снята, каким раундом."""

    sha256: str = Field(min_length=1)
    at: datetime
    round: int = Field(ge=1)


RouteDocChangeName = Literal["same", "changed", "new"]


class RouteDoc(StrictModel):
    doc_id: str
    name: dict[str, str]
    frozen: bool
    slots: list[RouteDocSlot]
    # Версия на подписи; null у черновика, после отмены и у маршрута 0.20.0 без перенесённой версии.
    sent: RouteDocVersion | None
    # Рабочая сборка отличается от версии на подписи (без неё от снимка); у черновика и отменённого false.
    changed: bool


class RoutePersonOption(StrictModel):
    """Кого можно поставить на персону: `id` это `user_id` участника проекта или `invitation_id` приглашения."""

    kind: Literal["member", "invitation"]
    id: str
    name: str | None


class RoutePersonaCandidates(StrictModel):
    persona: str
    people: list[RoutePersonOption]


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
    # Из кого выбирать на персоны маршрута и его слотов; только тому, кто управляет маршрутом, иначе пусто.
    candidates: list[RoutePersonaCandidates]
    # Документы с `changed`, в порядке `docs`: есть что отправить новой версией (12.6).
    changed_docs: list[str]
    # Пресет точки (15.11): только тому, кто управляет маршрутом, у маршрута, который можно править
    # (`draft`, `paused`, `returned`, `cancelled`), и если шаблон пресет задаёт; иначе null.
    preset: RoutePreset | None


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
    # Документы маршрута (мягкое предупреждение правки, 12.7) и те, чья рабочая сборка ушла от версии на подписи.
    docs: list[str]
    changed_docs: list[str]


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
    # `build:<sha>` кандидата (текущей сборки, у несобранного документа его версии на подписи).
    token: str | None
    # Кандидат против версии на подписи (12.6).
    change: RouteDocChangeName
    sent: RouteDocVersion | None


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
    # Согласие переносится по всем его документам; false, если он ещё не согласовывал.
    keeps_approval: bool


class SigningRouteBlockerRoute(StrictModel):
    """Маршрут, который держит документ (`doc_in_other_route`): его точка и статус, чтобы назвать, что делать."""

    id: str
    profile: SigningProfileRef
    status: SigningRouteStatusName


class SigningRouteBlocker(StrictModel):
    code: str
    doc_id: str | None
    slot_id: str | None
    participant_id: str | None
    # Только у `doc_in_other_route`, иначе null.
    other_route: SigningRouteBlockerRoute | None


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
    # «Что изменилось» (12.6): заменяет сообщение маршрута; пробелы по краям обрезаются, пустое это null.
    note: str | None = Field(default=None, max_length=SIGNING_TEXT_MAX)


class SigningReminder(StrictModel):
    """Ответ «Напомнить». `link` только при `manual`: ссылку приглашения пересылает сам автор (без SMTP)."""

    participant_id: str
    delivery: Literal["email", "inbox", "manual"]
    link: str | None


class SigningLink(StrictModel):
    """Ответ «Скопировать ссылку»: что автор сам перешлёт подписанту.

    `kind`: `page` страница подписи участника с аккаунтом, `invitation` новая ссылка приглашения (прежняя перестаёт
    работать), `inbox` «Входящие» того, кого пригласили как аккаунт.
    """

    participant_id: str
    kind: Literal["page", "invitation", "inbox"]
    link: str


class EmptyRequest(StrictModel):
    """Тело действий без параметров (`{}`): предпросмотр, отмена, снятие с контроля."""


# --- задача подписанта (`.../task`) -----------------------------------------------------------------------------------


class SigningProjectRef(StrictModel):
    id: str
    name: str


class SigningTaskRoute(StrictModel):
    id: str
    project: SigningProjectRef
    profile: SigningProfileRef
    status: SigningRouteStatusName
    phase: SigningRoutePhaseName | None
    round: int = Field(ge=0)
    current_step: int | None = Field(ge=1)
    deadline: datetime | None
    message: str | None
    # Кто отправил маршрут; null, если аккаунта больше нет или маршрут ещё не отправлен.
    sender: str | None
    sent_at: datetime | None
    stop_reason: SigningStopReasonName | None
    # Раунд новой версии, в котором изменился хотя бы один документ участника (12.6).
    new_version: bool


class SigningTaskPerson(StrictModel):
    name: str | None
    persona: str
    state: ParticipantStateName
    # Последнее действие участника в этом раунде: согласие, подпись или возврат.
    at: datetime | None
    me: bool
    # Имя персоны по карточке проекта и меняет ли его согласие видимый слой, как у `RouteParticipant`.
    card_name: str | None
    changes_visible: bool


class SigningPlate(StrictModel):
    """Данные плашки подписанта: то, что на ней напечатано."""

    owner: str
    kind: SigningPlateKindName
    cert_id: str


class SigningTaskKeys(StrictModel):
    server_keys_allowed: bool
    default_key: SigningKeyInfo | None


class SigningTaskMe(StrictModel):
    participant_id: str
    state: ParticipantStateName
    next_action: SigningNextActionName
    # Способы, которые можно выбрать сейчас; после фиксации только текущий.
    methods: list[RouteSignMethodName]
    method: RouteSignMethodName | None
    image_ready: bool
    # Путь API от корня сайта к своей загруженной картинке (PNG) для предпросмотра; null, пока её нет.
    image_url: str | None
    plate: SigningPlate | None
    keys: SigningTaskKeys
    # Все оставшиеся пары участника необязательны на точке: автор может его пропустить (13.3).
    optional: bool


class SigningTaskDateMark(StrictModel):
    """Метка даты слота на документе задачи (14.7): место рамки и что напечатано сейчас; null у пустой метки
    (слот ещё не согласован, придержан или пропущен)."""

    page: int = Field(ge=1)
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    text: str | None


class SigningTaskOtherSlot(StrictModel):
    """Чужой слот на документе: место и статус, без причины плана."""

    slot_id: str
    label: dict[str, str]
    page: int = Field(ge=1)
    x_mm: float
    y_mm: float
    width_mm: float
    # Высота метки; null у слота без видимой метки (PAdES без картинки).
    height_mm: float | None
    mark: RouteVisibleMarkName
    status: RouteSlotStatusName
    # Метки даты слота на этом документе: страница подписи рисует рамки своих («Дата согласования»).
    dates: list[SigningTaskDateMark]


class SigningTaskSlot(SigningTaskOtherSlot):
    """Свой слот: ещё и причина плана (`PlanReason`), почему он не подписан; null у подписанного."""

    reason: str | None
    # Подпись необязательна на точке: пометка «необязательна» (13.9).
    optional: bool


class SigningTaskDoc(StrictModel):
    doc_id: str
    name: dict[str, str]
    # Путь API от корня сайта: до фиксации предпросмотр без придержанных картинок, после зафиксированный PDF.
    pdf_url: str = Field(min_length=1)
    frozen: bool
    # Отпечаток для `expected` следующего действия; null, когда действовать нечего.
    token: str | None
    mine: list[SigningTaskSlot]
    others: list[SigningTaskOtherSlot]
    # Дата версии на подписи («Вы подписываете версию от …»); null, если версии нет.
    sent_at: datetime | None
    # Документ изменился с прошлого согласия участника: согласовать заново.
    changed_since_mine: bool
    # Рабочая сборка ушла от версии на подписи; только автору и управляющим, остальным null.
    changed: bool | None


class SigningTask(StrictModel):
    """Задача подписанта: ответ чтения и всех его действий."""

    route: SigningTaskRoute
    steps: list[list[SigningTaskPerson]]
    me: SigningTaskMe
    docs: list[SigningTaskDoc]
    events: list[RouteEvent]


class ApproveSigningTaskRequest(StrictModel):
    expected: dict[str, str]
    # Сменить способ своих слотов (из `me.methods`); null: оставить.
    method: RouteSignMethodName | None = None
    # «Согласовать и подписать»: подписать свои слоты ЭП ключом Студии в том же запросе.
    sign: SigningKeyRequest | None = None


class SignSigningTaskRequest(StrictModel):
    expected: dict[str, str]
    identity_id: str | None = None
    passphrase: str | None = Field(default=None, max_length=PASSPHRASE_MAX)


class ReturnSigningTaskRequest(StrictModel):
    comment: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=SIGNING_TEXT_MAX)]


class SetSigningTaskPlateRequest(StrictModel):
    identity_id: str = Field(min_length=1, max_length=64)
