"""План подписей: ответы `GET /projects/{id}/signature-plan` (docs/design/signature-plan.md)."""

from __future__ import annotations

from pydantic import BaseModel

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


class PlanFrozenResponse(BaseModel):
    sha256: str
    source_sha256: str
    frozen_at: str
    # Есть встроенные подписи: итоговый файл длиннее зафиксированного, его начало совпадает с ним.
    signed_sha256: str = ""
    outdated: PlanReason | None = None


class DocPlanResponse(BaseModel):
    doc_id: str
    built: bool
    frozen: PlanFrozenResponse | None = None
    slots: list[PlanSlotResponse]


class SignaturePlanResponse(BaseModel):
    profile_id: str | None = None
    total: int
    signed: int
    crypto_total: int
    crypto_signed: int
    waiting_for_me: int
    docs: list[DocPlanResponse]


def _map_slot(slot: PlanSlot) -> PlanSlotResponse:
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
    )


def _map_doc(doc: DocPlan) -> DocPlanResponse:
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
        slots=[_map_slot(s) for s in doc.slots],
    )


def map_plan(plan: SignaturePlan) -> SignaturePlanResponse:
    crypto = [s for s in plan.slots if s.state.crypto]
    return SignaturePlanResponse(
        profile_id=plan.profile_id,
        total=plan.total,
        signed=plan.signed,
        crypto_total=len(crypto),
        crypto_signed=sum(1 for s in crypto if s.status is SlotStatus.signed),
        waiting_for_me=plan.waiting_for_me,
        docs=[_map_doc(d) for d in plan.docs],
    )
