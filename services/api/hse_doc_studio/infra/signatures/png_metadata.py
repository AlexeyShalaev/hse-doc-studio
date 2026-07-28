from __future__ import annotations

import struct
from pathlib import Path

import structlog

logger = structlog.get_logger()

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def is_png(blob: bytes) -> bool:
    return len(blob) >= 8 and blob[:8] == _PNG_MAGIC


def read_dimensions(path: Path) -> tuple[int, int] | None:
    """Return (width_px, height_px) by parsing the PNG IHDR chunk.

    We do not pull in Pillow just to read dimensions — IHDR is the first chunk
    after the 8-byte signature and contains width/height as big-endian uint32 at
    fixed offsets. Failure returns None and is treated as "use the slot default
    aspect ratio" by callers.
    """
    try:
        with path.open("rb") as fh:
            head = fh.read(24)
    except OSError as exc:
        logger.warning("png_metadata: read error", path=str(path), exc=str(exc))
        return None
    if len(head) < 24 or head[:8] != _PNG_MAGIC:
        return None
    try:
        width, height = struct.unpack(">II", head[16:24])
    except struct.error:
        return None
    return int(width), int(height)


def read_dimensions_from_bytes(blob: bytes) -> tuple[int, int] | None:
    if len(blob) < 24 or not is_png(blob):
        return None
    try:
        width, height = struct.unpack(">II", blob[16:24])
    except struct.error:
        return None
    return int(width), int(height)
