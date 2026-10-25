from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from hse_doc_studio.core.enums import DetachedFormat, DetachedOrigin, DetachedVerdict, SignMode


class SignerInfoResponse(BaseModel):
    kind: str
    owner: str
    cert_id: str
    valid_from: str | None
    valid_to: str | None
    signer_id: str
    level: str = ""


class LevelRequest(BaseModel):
    """PUT /signatures/slots/{slot_id}/signer/level."""

    level: str = ""


class ManualSignerRequest(BaseModel):
    """PUT /signatures/slots/{slot_id}/signer, JSON body: a signer typed in or taken from a Studio key."""

    identity_id: UUID | None = None
    owner: str = ""
    cert_id: str = ""
    valid_from: str | None = None
    valid_to: str | None = None
    level: str = ""


class SlotInfoResponse(BaseModel):
    png_path: str | None
    natural_width_px: int | None
    natural_height_px: int | None
    signing_identity_id: str | None = None
    sign_mode: SignMode = SignMode.image
    sign_reason: str = ""
    signer: SignerInfoResponse | None = None


class UpdateSlotConfigRequest(BaseModel):
    """PATCH /signatures/slots/{slot_id}/config — set crypto options for a slot."""

    signing_identity_id: str | None = None  # None = clear (image-only)
    sign_mode: SignMode = SignMode.image
    sign_reason: str = ""


class PlacementResponse(BaseModel):
    enabled: bool
    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    # ISO «2026-05-12»; печатается как «12.05.2026» рядом с подписью.
    sign_date: str | None = None


class ProfileRefResponse(BaseModel):
    """Контрольная точка, требующая эту подпись."""

    id: str
    name: dict[str, str]


class RuntimeSlotResponse(BaseModel):
    """Рантайм-слот проекта: team размножает per-author слоты пака в
    "{slot}--{slug}"; applies_to/required_by уже на уровне ИНСТАНСОВ доков."""

    id: str
    label: dict[str, str]
    applies_to: list[str]
    # Где подпись обязательна и НА КАКОЙ точке: id документа → контрольные
    # точки. Заменило прежнее `required_for: list[str]`: то поле объявлялось
    # у слота отдельно и разошлось с профилями сдачи — панель молчала о
    # подписях, которых финальный комплект требовал.
    required_by: dict[str, list[ProfileRefResponse]] = {}
    default_placement: dict[str, float]
    # Слаг автора-владельца per-author слота; None — обычный слот пака.
    owner: str | None = None


class FrozenPdfResponse(BaseModel):
    sha256: str
    size: int
    frozen_at: str
    # Signers or positions changed after freezing: the printed plate is out of date.
    plate_outdated: bool = False
    # The compiled PDF changed after freezing: signatures no longer belong to the document.
    stale: bool


class DetachedSignatureResponse(BaseModel):
    format: DetachedFormat
    origin: DetachedOrigin
    verdict: DetachedVerdict
    signer: str
    signer_id: str
    issuer: str
    algorithm: str
    signed_at: str | None
    not_before: str | None
    not_after: str | None
    chain: str | None
    # Stable codes the web app translates (see detached_verifier).
    notes: list[str]
    added_at: str
    file_name: str
    # False when the signature covers an older frozen PDF, or the document was rebuilt since.
    current: bool


class SignaturesStateResponse(BaseModel):
    slots: dict[str, SlotInfoResponse]
    placements: dict[str, dict[str, PlacementResponse]]
    frozen: dict[str, FrozenPdfResponse] = {}
    detached: dict[str, dict[str, DetachedSignatureResponse]] = {}
    # Пустой список у старых клиентов не ломает ничего: фронт падает обратно
    # на слоты каталога, когда рантайм-список отсутствует.
    runtime_slots: list[RuntimeSlotResponse] = []


class UpdatePlacementRequest(BaseModel):
    enabled: bool | None = None
    page: int | None = None
    x_mm: float | None = None
    y_mm: float | None = None
    width_mm: float | None = None
    # None — не менять; "" — очистить; иначе ISO «2026-05-12».
    sign_date: str | None = None


class UploadSignatureResponse(BaseModel):
    png_path: str
    natural_width_px: int | None
    natural_height_px: int | None


class FreezePdfResponse(BaseModel):
    frozen: FrozenPdfResponse
    dropped_slots: list[str]


class AttachDetachedSignatureResponse(BaseModel):
    signature: DetachedSignatureResponse
    # OpenPGP signature by a key the keyring lacks: the key id to ask the signer's public key for.
    missing_key_id: str | None = None


class SignInStudioRequest(BaseModel):
    identity_id: UUID
    passphrase: str = ""
