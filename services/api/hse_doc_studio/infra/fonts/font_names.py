"""Minimal, dependency-free reader for a font's family name (sfnt `name` table).

Used to label system fonts with their family so the UI can preview them by name
(the font is OS-installed, so the browser renders it natively). Best-effort:
any malformed/unsupported file yields None rather than raising. Avoids pulling in
fontTools just for this.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO

# Prefer the typographic family (nameID 16) over the legacy family (nameID 1).
_FAMILY_NAME_IDS = (16, 1)
# Decode preference by platform: Windows (3) and Unicode (0) are UTF-16BE; Mac (1)
# is Mac Roman. Lower number = higher preference.
_PLATFORM_PRIORITY = {3: 0, 0: 1, 1: 2}


def _decode(platform_id: int, raw: bytes) -> str | None:
    try:
        if platform_id in (0, 3):
            return raw.decode("utf-16-be")
        if platform_id == 1:
            return raw.decode("mac-roman")
    except (UnicodeDecodeError, LookupError):
        return None
    return None


def _name_table_location(fh: BinaryIO, font_offset: int) -> tuple[int, int] | None:
    """(offset, length) of the `name` table within the file, or None."""
    fh.seek(font_offset)
    offset_table = fh.read(12)
    if len(offset_table) < 12:
        return None
    num_tables = struct.unpack(">H", offset_table[4:6])[0]
    directory = fh.read(16 * num_tables)
    for i in range(num_tables):
        rec = directory[i * 16 : (i + 1) * 16]
        if len(rec) < 16:
            break
        if rec[0:4] == b"name":
            off, length = struct.unpack(">II", rec[8:16])
            return off, length
    return None


def _best_family(table: bytes) -> str | None:
    """Pick the best family name from a raw `name` table."""
    if len(table) < 6:
        return None
    count, string_offset = struct.unpack(">HH", table[2:6])
    best: tuple[tuple[int, int], str] | None = None
    for i in range(count):
        rec = table[6 + i * 12 : 6 + (i + 1) * 12]
        if len(rec) < 12:
            break
        platform_id, _enc, _lang, name_id, length, offset = struct.unpack(">HHHHHH", rec)
        if name_id not in _FAMILY_NAME_IDS:
            continue
        start = string_offset + offset
        value = _decode(platform_id, table[start : start + length])
        if value is None or not value.strip():
            continue
        priority = (0 if name_id == 16 else 1, _PLATFORM_PRIORITY.get(platform_id, 9))
        if best is None or priority < best[0]:
            best = (priority, value.strip())
    return best[1] if best is not None else None


def read_family_name(path: Path) -> str | None:
    try:
        with path.open("rb") as fh:
            font_offset = 0
            if fh.read(4) == b"ttcf":  # TrueType Collection — read the first font
                fh.seek(12)
                font_offset = struct.unpack(">I", fh.read(4))[0]
            located = _name_table_location(fh, font_offset)
            if located is None:
                return None
            name_off, name_len = located
            fh.seek(name_off)
            return _best_family(fh.read(name_len))
    except (OSError, struct.error):
        return None
