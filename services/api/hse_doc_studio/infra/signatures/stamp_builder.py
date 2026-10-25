"""Turns a project's signature state into the stamps for one document."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import structlog

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.infra.signatures.pdf_stamper import Stamp, format_sign_date

logger = structlog.get_logger()

# What the memo «КП и ВКР на СПИ» asks to print in the signature field when the
# document is signed with a detached electronic signature.
DETACHED_CAPTION = {
    "ru": "Подписано с помощью открепленной электронной подписи",
    "en": "Signed with a detached electronic signature",
}

_DEFAULT_ASPECT = 0.4


def detached_caption(lang: str) -> str:
    return DETACHED_CAPTION.get(lang) or DETACHED_CAPTION["ru"]


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
