"""Метки на PDF и их построение из состояния подписей: чистые данные без reportlab."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from pathlib import Path, PurePath

import structlog

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo

logger = structlog.get_logger()


# Плашка открепленной ЭП на рамке картинки (около 30 мм) переносится на 7-8 строк. Столько же даёт редактор размещения,
# когда автор включает место слота с ЭП (`MIN_CAPTION_WIDTH_MM` на фронтенде).
PLATE_MIN_WIDTH_MM = 70.0


def widen_for_plate(state: SignaturesState, pairs: Iterable[tuple[str, str]]) -> SignaturesState:
    """Места пар «документ, слот» не уже плашки: узкое место расширяется до `PLATE_MIN_WIDTH_MM`.

    Правый край рамки остаётся на месте, левый уходит влево (не левее края страницы): подписи обычно стоят у правого
    поля, и рамка, растущая вправо, вышла бы за страницу. Выключенные и уже широкие места не трогаются.
    """
    placements = {doc_id: dict(slot_map) for doc_id, slot_map in state.placements.items()}
    touched = False
    for doc_id, slot_id in pairs:
        placement = placements.get(doc_id, {}).get(slot_id)
        if placement is None or not placement.enabled or placement.width_mm >= PLATE_MIN_WIDTH_MM:
            continue
        right = placement.x_mm + placement.width_mm
        placements[doc_id][slot_id] = replace(
            placement, x_mm=max(0.0, right - PLATE_MIN_WIDTH_MM), width_mm=PLATE_MIN_WIDTH_MM
        )
        touched = True
    return replace(state, placements=placements) if touched else state


def format_sign_date(iso_date: str | None) -> str | None:
    """ISO «2026-05-12» → печатное «12.05.2026»; None/пусто → None."""
    if not iso_date:
        return None
    try:
        return date.fromisoformat(iso_date).strftime("%d.%m.%Y")
    except ValueError:
        # Свободный формат из старых данных — печатаем как есть.
        return iso_date


@dataclass(frozen=True)
class Stamp:
    """A single PNG or text mark to place on a PDF page.

    Coordinates are in millimetres from the **top-left** corner of the page —
    the natural convention for the UI overlay layer. The stamper handles the
    flip to PDF native coords (bottom-left origin, points) internally so
    callers don't have to think about it.
    """

    page: int  # 1-indexed
    x_mm: float
    y_mm: float
    width_mm: float
    png_path: Path | None
    aspect_ratio: float  # height / width — preserves uploaded PNG proportions
    # Text mark instead of a PNG: a framed, wrapped caption (the date, when
    # set, goes on its own last line inside the frame).
    text: str | None = None
    # Signature plate rows («Сертификат», «Владелец», ...) under the bold caption.
    details: tuple[tuple[str, str], ...] = ()
    # Second bold line under the caption (the signature level), empty = none.
    subtitle: str = ""
    # Label of the date row when the plate has details («Дата подписания»).
    date_label: str = ""
    # Signing date rendered as text to the right of the PNG («12.05.2026»).
    # ASCII-only by design so the built-in Helvetica suffices.
    date_text: str | None = None
    # Slot the mark belongs to, for error messages only: not part of the visible layer, so it stays out of
    # equality, `repr` and the fingerprints (`stamps_digest`, `legacy_stamps_digest`).
    slot_id: str | None = field(default=None, repr=False, compare=False)


# What the memo «КП и ВКР на СПИ» asks to print in the signature field when the
# document is signed with a detached electronic signature.
DETACHED_CAPTION = {
    "ru": "Подписано с помощью открепленной электронной подписи",
    "en": "Signed with a detached electronic signature",
}

_DEFAULT_ASPECT = 0.4


def detached_caption(lang: str) -> str:
    return DETACHED_CAPTION.get(lang) or DETACHED_CAPTION["ru"]


_LABELS = {
    "ru": {
        "x509": "Сертификат",
        "openpgp": "Ключ",
        "owner": "Владелец",
        "valid": "Действителен",
        "from": "с",
        "to": "по",
        "until": "до",
        "date": "Дата подписания",
    },
    "en": {
        "x509": "Certificate",
        "openpgp": "Key",
        "owner": "Owner",
        "valid": "Valid",
        "from": "from",
        "to": "to",
        "until": "until",
        "date": "Signing date",
    },
}


_LEVELS = {
    "ru": {
        "ukep": "Усиленная квалифицированная электронная подпись",
        "unep": "Усиленная неквалифицированная электронная подпись",
    },
    "en": {"ukep": "Enhanced qualified electronic signature", "unep": "Enhanced non-qualified electronic signature"},
}


def level_subtitle(signer: SignerInfo | None, lang: str) -> str:
    if signer is None or not signer.level:
        return ""
    return (_LEVELS.get(lang) or _LEVELS["ru"]).get(signer.level, "")


def date_row_label(lang: str) -> str:
    return (_LABELS.get(lang) or _LABELS["ru"])["date"]


def signer_details(signer: SignerInfo | None, lang: str) -> tuple[tuple[str, str], ...]:
    """Rows of the signature plate for the expected signer, like the HSE e-signature stamp."""
    if signer is None:
        return ()
    labels = _LABELS.get(lang) or _LABELS["ru"]
    rows: list[tuple[str, str]] = []
    if signer.cert_id:
        rows.append((labels["openpgp" if signer.kind == "openpgp" else "x509"], signer.cert_id))
    if signer.owner:
        rows.append((labels["owner"], signer.owner))
    start, end = (
        format_sign_date(signer.valid_from[:10] if signer.valid_from else None),
        format_sign_date(signer.valid_to[:10] if signer.valid_to else None),
    )
    if start and end:
        rows.append((labels["valid"], f"{labels['from']} {start} {labels['to']} {end}"))
    elif end:
        rows.append((labels["valid"], f"{labels['until']} {end}"))
    return tuple(rows)


def _project_relative(path: PurePath | None, root: PurePath) -> str | None:
    """Путь картинки относительно папки проекта в POSIX-виде: не зависит от того, где лежит проект и на какой ОС."""
    if path is None:
        return None
    return (path.relative_to(root) if path.is_relative_to(root) else path).as_posix()


def _digest_row(stamp: Stamp, root: PurePath) -> dict[str, object]:
    row = {**asdict(stamp), "png_path": _project_relative(stamp.png_path, root)}
    del row["slot_id"]
    return row


def stamps_digest(stamps: Sequence[Stamp], root: PurePath) -> str:
    """Отпечаток видимого слоя: меняется, когда меняется подписант, положение, дата или картинка слота.

    Картинка входит путём относительно `root` (папки проекта), а не абсолютным: перенос папки проекта, другой
    каталог данных у локальной Студии и облака или другая ОС отпечаток не меняют.
    """
    rows = [_digest_row(stamp, root) for stamp in stamps]
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def legacy_stamps_digest(stamps: Sequence[Stamp]) -> str:
    """Отпечаток прежнего вида: sha256 от `repr` меток с абсолютным путём картинки.

    Такие отпечатки записаны у фиксаций, сделанных до перехода на относительные пути. Новые не пишутся,
    функция нужна только для сверки (`stamps_digest_matches`).
    """
    return hashlib.sha256(repr(list(stamps)).encode()).hexdigest()


def stamps_digest_matches(stored: str, stamps: Sequence[Stamp], root: PurePath) -> bool:
    """Записанный при фиксации отпечаток совпадает с видимым слоем, который поставила бы фиксация сейчас.

    Пустой отпечаток (фиксация до появления отпечатков) совпадает всегда. Отпечаток прежнего вида принимается,
    если совпадает с прежней формулой на текущих метках: после обновления подписи не устаревают сами собой.
    """
    if not stored:
        return True
    return stored in (stamps_digest(stamps, root), legacy_stamps_digest(stamps))


def stamps_for_doc(
    state: SignaturesState,
    doc_id: str,
    project_folder: Path,
    lang: str,
    slot_ids: Iterable[str] | None = None,
    png_exists: Callable[[Path], bool] | None = None,
) -> list[Stamp]:
    """Stamps for every enabled placement of `doc_id` (optionally limited to `slot_ids`).

    A `detached_text` slot prints the caption; any other slot with an uploaded PNG
    prints the picture. Slots with neither are skipped, and so are slots withheld by
    a signing route (`state.withheld`): the mark waits for the signer's approval and
    is left out of the preview, the signed copy, the signer pack, the freeze and the
    visible-layer fingerprint. `png_exists` replaces the disk check (the planner
    looks at the project through its own probe).
    """
    exists = png_exists or Path.exists
    wanted = set(slot_ids) if slot_ids is not None else None
    result: list[Stamp] = []
    for slot_id, placement in state.placements.get(doc_id, {}).items():
        skipped = not placement.enabled or (wanted is not None and slot_id not in wanted)
        if skipped or state.is_withheld(doc_id, slot_id):
            continue
        slot = state.slots.get(slot_id)
        if slot is not None and slot.sign_mode is SignMode.detached_text:
            result.append(
                Stamp(
                    page=placement.page,
                    x_mm=placement.x_mm,
                    y_mm=placement.y_mm,
                    width_mm=placement.width_mm,
                    png_path=None,
                    aspect_ratio=_DEFAULT_ASPECT,
                    text=detached_caption(lang),
                    details=signer_details(slot.signer, lang),
                    subtitle=level_subtitle(slot.signer, lang),
                    date_label=date_row_label(lang),
                    date_text=format_sign_date(placement.sign_date),
                    slot_id=slot_id,
                )
            )
            continue
        if slot is None or slot.png_path is None:
            continue
        png_path = project_folder / slot.png_path
        if not exists(png_path):
            logger.warning("stamps: PNG missing for slot", doc_id=doc_id, slot_id=slot_id, path=str(png_path))
            continue
        aspect = _DEFAULT_ASPECT
        if slot.natural_width_px and slot.natural_height_px and slot.natural_width_px > 0:
            aspect = slot.natural_height_px / slot.natural_width_px
        result.append(
            Stamp(
                page=placement.page,
                x_mm=placement.x_mm,
                y_mm=placement.y_mm,
                width_mm=placement.width_mm,
                png_path=png_path,
                aspect_ratio=aspect,
                date_text=format_sign_date(placement.sign_date),
                slot_id=slot_id,
            )
        )
    return result
