from __future__ import annotations

from pydantic import BaseModel

from hse_doc_studio.core.enums import SignMode


class SlotInfoResponse(BaseModel):
    png_path: str | None
    natural_width_px: int | None
    natural_height_px: int | None
    signing_identity_id: str | None = None
    sign_mode: SignMode = SignMode.image
    sign_reason: str = ""


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


class SignaturesStateResponse(BaseModel):
    slots: dict[str, SlotInfoResponse]
    placements: dict[str, dict[str, PlacementResponse]]
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
