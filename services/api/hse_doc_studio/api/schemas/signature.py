from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.enums import (
    DateMarkAlign,
    DateMarkFormat,
    DetachedFormat,
    DetachedOrigin,
    DetachedVerdict,
    PlacementOrigin,
    SignedAtSource,
    SignMode,
)


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


class DateMarkResponse(StrictModel):
    """Метка даты подписания слота (signing-route.md, 14.3 и 14.7): рамка, формат и что напечатано сейчас."""

    id: str
    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    format: DateMarkFormat
    align: DateMarkAlign
    # Что будет напечатано сейчас; null, если метка пустая (нет даты подписи, подпись придержана или пропущена).
    text: str | None


class SignedAtResponse(StrictModel):
    """Момент подписи слота в документе (14.3): ISO 8601, у ручной даты только день («2026-11-13»)."""

    at: str
    source: SignedAtSource


class PlacementResponse(StrictModel):
    enabled: bool
    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    # ISO «2026-05-12»; печатается как «12.05.2026» рядом с подписью.
    sign_date: str | None = None
    # Метки даты подписания слота (signing-route.md, 14.7); правит их только `PUT .../dates`.
    dates: list[DateMarkResponse] = []
    signed_at: SignedAtResponse | None = None
    # Откуда место (signing-route.md, 15.4 и 15.11): `pack` как в шаблоне, `seed` затравка из пака, которую никто не
    # трогал, `manual` поставил или изменил автор.
    origin: PlacementOrigin = PlacementOrigin.manual
    # В шаблоне проекта есть место этого слота для документа: по нему «Вернуть место из шаблона» (15.6).
    preset_available: bool = False


class PackPlaceResponse(StrictModel):
    """Место слота на документе из пака (signing-route.md, 15.3): `placements` документа, иначе `default_placement`."""

    page: int
    x_mm: float
    y_mm: float
    width_mm: float


class PackDateMarkResponse(StrictModel):
    """Метка даты слота на документе из пака (`default_dates`, 14.10): рамка и формат, без id и текста."""

    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    format: DateMarkFormat
    align: DateMarkAlign


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
    # Пак запрещает отмечать подпись необязательной (`required: true`, signing-route.md, 13.3).
    required: bool = False
    # Точки, чей маршрут включил слот в документ сверх точки: id документа → точки (13.6).
    extra_by: dict[str, list[ProfileRefResponse]] = {}
    # Место из пака по экземплярам документов из `applies_to` (signing-route.md, 15.11); `default_placement` остаётся
    # общим местом слота для старых клиентов.
    default_placements: dict[str, PackPlaceResponse] = {}
    # Метки даты из пака по экземплярам документов; документа без меток в словаре нет.
    default_dates: dict[str, list[PackDateMarkResponse]] = {}


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
    # A self-signed root the chain ends in that is not trusted yet (to be confirmed by the user).
    root_subject: str = ""
    root_fingerprint: str = ""
    # Stable codes the web app translates (see detached_verifier).
    notes: list[str]
    added_at: str
    file_name: str
    # False when the signature covers an older frozen PDF, or the document was rebuilt since.
    current: bool


class SkippedSlotResponse(BaseModel):
    """Пропуск подписи маршрутом (signing-route.md, 13.3)."""

    profile_id: str
    route_id: str
    round: int
    at: str
    # Метка осталась в зафиксированном PDF, над которым уже есть ЭП (13.5).
    keep_mark: bool


class SignaturesStateResponse(BaseModel):
    slots: dict[str, SlotInfoResponse]
    placements: dict[str, dict[str, PlacementResponse]]
    frozen: dict[str, FrozenPdfResponse] = {}
    detached: dict[str, dict[str, DetachedSignatureResponse]] = {}
    # Пустой список у старых клиентов не ломает ничего: фронт падает обратно
    # на слоты каталога, когда рантайм-список отсутствует.
    runtime_slots: list[RuntimeSlotResponse] = []
    # Слоты документов, чью картинку придержал маршрут подписания до согласия подписанта (signing-route.md, 6.1):
    # на вкладке «Подписи» у них пометка «Придержано маршрутом» и «Показать» (5.6).
    withheld: dict[str, list[str]] = {}
    # Необязательные подписи (signing-route.md, 13.3): документ → точка → слоты, которые на ней можно не подписывать.
    optional: dict[str, dict[str, list[str]]] = {}
    # Пропущенные маршрутом подписи: документ → слот → пропуск.
    skipped: dict[str, dict[str, SkippedSlotResponse]] = {}


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


class EmbeddedSignatureResponse(BaseModel):
    """Встроенная подпись PAdES слота: поле в PDF и что о ней сказала проверка."""

    field_name: str
    verdict: DetachedVerdict
    signer: str
    signer_id: str
    signed_at: str | None = None
    revision_size: int
    notes: list[str] = []


class SetSlotOptionalRequest(StrictModel):
    """PUT /signatures/optional/{doc_id}/{slot_id}: отметить или снять «Подпись необязательна» на точке (13.6)."""

    profile_id: str
    optional: bool


class SlotOptional(StrictModel):
    """Ответ на отметку: что стало с парой на точке (signing-route.md, 13.6)."""

    doc_id: str
    slot_id: str
    profile_id: str
    optional: bool
    # Подписанта уже пропустили на этой точке.
    skipped: bool
    # Отметку сняли у пропущенной пары, а маршрут держит документ: подписант вернётся при следующей отправке.
    returns_next_round: bool


# Формат и выравнивание метки приходят строкой: незнакомое значение это 400 `bad_date_mark` сценария, а не 422 схемы.
_FORMAT = Annotated[str, Field(json_schema_extra={"enum": [f.value for f in DateMarkFormat]})]
_ALIGN = Annotated[str, Field(json_schema_extra={"enum": [a.value for a in DateMarkAlign]})]


class DateMarkRequest(StrictModel):
    """Метка даты в `PUT .../dates`: `id` null у новой (сервер выдаст `d1`, `d2`, ...)."""

    id: str | None = None
    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    format: _FORMAT
    align: _ALIGN = DateMarkAlign.centered.value


class ManualSignedAtRequest(StrictModel):
    """Ручная дата подписи слота вне маршрута: день ISO «2026-11-13»."""

    date: str


class SetDateMarksRequest(StrictModel):
    """PUT /signatures/placements/{doc_id}/{slot_id}/dates: метки даты слота документа целиком (14.7).

    `signed_at` не передано: дата подписи не меняется; null: снять ручную дату; `{date}`: поставить её. Только вне
    маршрута: на паре участника маршрута 409 `date_from_route`. `confirm_reset` подтверждение сброса подписей
    сценарием маршрута (срез R23); вне маршрута не нужно.
    """

    dates: list[DateMarkRequest] = Field(max_length=64)
    signed_at: ManualSignedAtRequest | None = None
    confirm_reset: bool = False


class RestorePlacementRequest(StrictModel):
    """POST /signatures/placements/{doc_id}/{slot_id}/restore: «Вернуть место из шаблона» (signing-route.md, 15.6).

    Место и метки даты слота документа как в шаблоне, `enabled` не меняется. `confirm_reset` подтверждение сброса
    ЭП над зафиксированным PDF документа, который держит идущий или завершённый маршрут (как у меток даты, 14.6).
    """

    confirm_reset: bool = False
