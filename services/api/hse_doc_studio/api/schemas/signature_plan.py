"""План подписей: ответы `GET /projects/{id}/signature-plan` (docs/design/signature-plan.md)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from hse_doc_studio.core.enums import DetachedVerdict, SignMode
from hse_doc_studio.core.signatures.plan import (
    DocPlan,
    PlanReason,
    PlanSlot,
    SignaturePlan,
    SignMethod,
    SlotStatus,
    VisibleMark,
)
from hse_doc_studio.core.signing_route.entities import DocSlot, ParticipantState, RoutePhase, RouteStatus, StopReason
from hse_doc_studio.core.signing_route.ports import PlanRoute, PlanRoutes
from hse_doc_studio.use_cases.signatures.sign_submission import SignSubmissionOutput, SignSubmissionPreview


class SlotCheckResponse(BaseModel):
    format: str
    verdict: DetachedVerdict
    signer: str
    signer_id: str
    signed_at: str | None = None
    notes: list[str] = []


class PlanSignerResponse(BaseModel):
    persona: str
    name: str


class PlanSlotResponse(BaseModel):
    slot_id: str
    label: dict[str, str]
    signer: PlanSignerResponse
    mode: SignMode
    method: SignMethod
    # Криптографическая подпись (открепленная или PAdES) или графическая картинка.
    crypto: bool
    mark: VisibleMark
    status: SlotStatus
    reason: PlanReason | None = None
    hint: str = ""
    allowed_methods: list[str] = []
    required_by: list[str] = []
    is_mine: bool = False
    check: SlotCheckResponse | None = None
    # Состояние участника маршрута подписания, которому принадлежит слот (signing-route.md, 6.1); без маршрута null.
    route_state: ParticipantState | None = None


class PlanFrozenResponse(BaseModel):
    sha256: str
    source_sha256: str
    frozen_at: str
    # Есть встроенные подписи: итоговый файл длиннее зафиксированного, его начало совпадает с ним.
    signed_sha256: str = ""
    outdated: PlanReason | None = None


class PlanPinnedResponse(BaseModel):
    """Версия на подписи документа (signing-route.md, 12.3): что подписывают вместо текущей сборки."""

    sha256: str
    pinned_at: str
    # Какой маршрут и раунд сняли версию; пустая строка и 0, если неизвестно.
    route_id: str
    round: int


class DocPlanResponse(BaseModel):
    doc_id: str
    # Есть источник подписи: версия на подписи или собранный PDF.
    built: bool
    frozen: PlanFrozenResponse | None = None
    slots: list[PlanSlotResponse]
    # Документ держит идущий маршрут подписания: фиксирует его только маршрут, сам по себе он не «устарел».
    held_by_route: bool = False
    # Версия на подписи; null, если документ подписывается по текущей сборке (12.4).
    pinned: PlanPinnedResponse | None = None
    # Рабочая сборка собрана и отличается от версии на подписи: «Есть изменения после отправки на подпись».
    working_differs: bool = False


class PlanRouteResponse(BaseModel):
    """Маршрут подписания точки сдачи или документа: состояние по расчёту на текущих файлах (signing-route.md, 6.1)."""

    id: UUID
    profile_id: str
    status: RouteStatus
    phase: RoutePhase | None = None
    round: int
    # Номер текущего шага по порядку (с 1); null вне идущего маршрута.
    current_step: int | None = None
    steps_total: int
    stop_reason: StopReason | None = None
    # Документы маршрута, рабочая сборка которых ушла от версии на подписи (12.9): «Есть изменения после отправки».
    changed_docs: list[str] = Field(default_factory=list)


class SignaturePlanResponse(BaseModel):
    profile_id: str | None = None
    total: int
    signed: int
    crypto_total: int
    crypto_signed: int
    waiting_for_me: int
    docs: list[DocPlanResponse]
    # Маршрут, который держит документы точки (`profile_id`) или документ (`doc_id`); иначе и без маршрутов null.
    route: PlanRouteResponse | None = None


def _map_route(route: PlanRoute) -> PlanRouteResponse:
    return PlanRouteResponse(
        id=route.id,
        profile_id=route.profile_id,
        status=route.status,
        phase=route.phase,
        round=route.round,
        current_step=route.current_step,
        steps_total=route.steps_total,
        stop_reason=route.stop_reason,
        changed_docs=list(route.changed_docs),
    )


def _map_slot(slot: PlanSlot, routes: PlanRoutes) -> PlanSlotResponse:
    check = slot.state.check
    return PlanSlotResponse(
        slot_id=slot.slot_id,
        label=slot.label,
        signer=PlanSignerResponse(persona=slot.signer.persona, name=slot.signer.name),
        mode=slot.mode,
        method=slot.state.method,
        crypto=slot.state.crypto,
        mark=slot.state.mark,
        status=slot.status,
        reason=slot.state.reason,
        hint=slot.hint,
        allowed_methods=list(slot.allowed_methods),
        required_by=list(slot.required_by),
        is_mine=slot.is_mine,
        check=SlotCheckResponse(
            format=check.format,
            verdict=check.verdict,
            signer=check.signer,
            signer_id=check.signer_id,
            signed_at=check.signed_at,
            notes=list(check.notes),
        )
        if check is not None
        else None,
        route_state=routes.slot_states.get(DocSlot(slot.doc_id, slot.slot_id)),
    )


def _map_doc(doc: DocPlan, routes: PlanRoutes) -> DocPlanResponse:
    frozen = doc.frozen
    return DocPlanResponse(
        doc_id=doc.doc_id,
        built=doc.built,
        frozen=PlanFrozenResponse(
            sha256=frozen.sha256,
            source_sha256=frozen.source_sha256,
            frozen_at=frozen.frozen_at,
            signed_sha256=frozen.signed_sha256,
            outdated=doc.frozen_outdated,
        )
        if frozen is not None
        else None,
        slots=[_map_slot(s, routes) for s in doc.slots],
        held_by_route=doc.doc_id in routes.held_docs,
        pinned=PlanPinnedResponse(
            sha256=pinned.sha256, pinned_at=pinned.pinned_at, route_id=pinned.route_id, round=pinned.round
        )
        if (pinned := doc.pinned) is not None
        else None,
        working_differs=doc.working_differs,
    )


def map_plan(plan: SignaturePlan, routes: PlanRoutes | None = None) -> SignaturePlanResponse:
    routes = routes or PlanRoutes()
    crypto = [s for s in plan.slots if s.state.crypto]
    return SignaturePlanResponse(
        profile_id=plan.profile_id,
        total=plan.total,
        signed=plan.signed,
        crypto_total=len(crypto),
        crypto_signed=sum(1 for s in crypto if s.status is SlotStatus.signed),
        # Слот документа идущего маршрута ждёт человека, только когда маршрут ждёт его самого: иначе счётчик
        # звал бы подписать то, что сейчас подписать нельзя.
        waiting_for_me=sum(
            1
            for s in plan.slots
            if s.is_mine and s.status is not SlotStatus.signed and routes.is_turn(s.doc_id, s.slot_id)
        ),
        docs=[_map_doc(d, routes) for d in plan.docs],
        route=_map_route(routes.route) if routes.route is not None else None,
    )


class SignSubmissionRequest(BaseModel):
    profile_id: str
    author: str | None = None
    identity_id: UUID | None = None
    # Пароль ключа OpenPGP: только на время подписи, не сохраняется и не пишется в лог.
    passphrase: str = Field(default="", max_length=500, repr=False)
    confirm_reset: bool = False
    expected: dict[str, str] | None = None


class KeyInfoResponse(BaseModel):
    id: UUID
    label: str
    kind: str
    protected: bool
    auto: bool
    signer: str


class ResetItemResponse(BaseModel):
    slot_id: str
    label: dict[str, str]
    signer: str
    method: str


class SlotActionResponse(BaseModel):
    slot_id: str
    label: dict[str, str]
    method: SignMethod
    status: SlotStatus
    action: str
    blocker: str = ""


class DocPreviewResponse(BaseModel):
    doc_id: str
    token: str
    needs_freeze: bool
    can_freeze: bool
    resets: list[ResetItemResponse]
    slots: list[SlotActionResponse]
    blocker: str = ""
    # Идущий маршрут подписания держит документ: ссылка на страницу подписи `/sign/{project}/{route}`.
    route_id: UUID | None = None


class SignPreviewResponse(BaseModel):
    profile_id: str
    key: KeyInfoResponse | None
    needs_passphrase: bool
    to_sign: int
    docs: list[DocPreviewResponse]


class SlotResultResponse(BaseModel):
    doc_id: str
    slot_id: str
    ok: bool
    message: str = ""


class SignSubmissionResponse(BaseModel):
    frozen_docs: list[str]
    results: list[SlotResultResponse]
    plan: SignaturePlanResponse


def map_preview(preview: SignSubmissionPreview) -> SignPreviewResponse:
    key = preview.key
    return SignPreviewResponse(
        profile_id=preview.profile_id,
        key=KeyInfoResponse(
            id=key.id, label=key.label, kind=key.kind, protected=key.protected, auto=key.auto, signer=key.signer
        )
        if key is not None
        else None,
        needs_passphrase=preview.needs_passphrase,
        to_sign=preview.to_sign,
        docs=[
            DocPreviewResponse(
                doc_id=d.doc_id,
                token=d.token,
                needs_freeze=d.needs_freeze,
                can_freeze=d.can_freeze,
                resets=[
                    ResetItemResponse(slot_id=r.slot_id, label=r.label, signer=r.signer, method=r.method)
                    for r in d.resets
                ],
                slots=[
                    SlotActionResponse(
                        slot_id=s.slot_id,
                        label=s.label,
                        method=s.method,
                        status=s.status,
                        action=s.action,
                        blocker=s.blocker,
                    )
                    for s in d.slots
                ],
                blocker=d.blocker,
                route_id=d.route_id,
            )
            for d in preview.docs
        ],
    )


def map_results(
    out: SignSubmissionOutput, plan: SignaturePlan, routes: PlanRoutes | None = None
) -> SignSubmissionResponse:
    return SignSubmissionResponse(
        frozen_docs=list(out.frozen_docs),
        results=[
            SlotResultResponse(doc_id=r.doc_id, slot_id=r.slot_id, ok=r.ok, message=r.message) for r in out.results
        ],
        plan=map_plan(plan, routes),
    )
