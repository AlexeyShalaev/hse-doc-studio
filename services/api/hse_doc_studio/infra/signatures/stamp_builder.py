"""Построение меток из состояния подписей перенесено в core.signatures.stamps."""

from __future__ import annotations

from hse_doc_studio.core.signatures.stamps import (
    DETACHED_CAPTION,
    date_row_label,
    detached_caption,
    level_subtitle,
    signer_details,
    stamps_digest,
    stamps_for_doc,
)

__all__ = [
    "DETACHED_CAPTION",
    "date_row_label",
    "detached_caption",
    "level_subtitle",
    "signer_details",
    "stamps_digest",
    "stamps_for_doc",
]
