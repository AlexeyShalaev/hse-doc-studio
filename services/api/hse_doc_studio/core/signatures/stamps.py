"""Метки на PDF и их построение из состояния подписей: чистые данные без reportlab."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import structlog

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo

logger = structlog.get_logger()


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


def stamps_digest(stamps: list[Stamp]) -> str:
    """Stable hash of what gets printed: changes when a signer, a position or a date changes."""
    return hashlib.sha256(repr(stamps).encode()).hexdigest()


def stamps_for_doc(
    state: SignaturesState,
    doc_id: str,
    project_folder: Path,
    lang: str,
    slot_ids: Iterable[str] | None = None,
) -> list[Stamp]:
    """Stamps for every enabled placement of `doc_id` (optionally limited to `slot_ids`).

    A `detached_text` slot prints the caption; any other slot with an uploaded PNG
    prints the picture. Slots with neither are skipped.
    """
    wanted = set(slot_ids) if slot_ids is not None else None
    result: list[Stamp] = []
    for slot_id, placement in state.placements.get(doc_id, {}).items():
        if not placement.enabled or (wanted is not None and slot_id not in wanted):
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
                )
            )
            continue
        if slot is None or slot.png_path is None:
            continue
        png_path = project_folder / slot.png_path
        if not png_path.exists():
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
            )
        )
    return result
