from __future__ import annotations

import struct
from pathlib import Path

import pytest
from hse_doc_studio.infra.fonts.font_names import read_family_name
from pytest_lazy_fixtures import lf

pytestmark = pytest.mark.unit


def _make_font(family: str, *, name_id: int = 1, platform_id: int = 3) -> bytes:
    """Build a minimal valid sfnt with a single `name` record holding `family`."""
    value = family.encode("utf-16-be") if platform_id in (0, 3) else family.encode("mac-roman")
    string_offset = 6 + 12  # name header (6) + one 12-byte record
    record = struct.pack(">HHHHHH", platform_id, 1, 0x409, name_id, len(value), 0)
    name_table = struct.pack(">HHH", 0, 1, string_offset) + record + value

    offset_table = struct.pack(">IHHHH", 0x00010000, 1, 0, 0, 0)
    name_off = 12 + 16  # offset table (12) + one 16-byte directory record
    directory = struct.pack(">4sIII", b"name", 0, name_off, len(name_table))
    return offset_table + directory + name_table


def test__read_family_name__cyrillic_family_name__returns_decoded_name(tmp_path: Path) -> None:
    p = tmp_path / "f.ttf"
    p.write_bytes(_make_font("Таймс Test"))
    assert read_family_name(p) == "Таймс Test"


def test__read_family_name__id1_and_id16_both_present__prefers_typographic_id16(tmp_path: Path) -> None:
    # Two records: nameID 1 = "Legacy", nameID 16 = "Typographic" → id16 wins.
    legacy = "Legacy".encode("utf-16-be")
    typo = "Typographic".encode("utf-16-be")
    string_offset = 6 + 24  # header + two 12-byte records
    rec1 = struct.pack(">HHHHHH", 3, 1, 0x409, 1, len(legacy), 0)
    rec16 = struct.pack(">HHHHHH", 3, 1, 0x409, 16, len(typo), len(legacy))
    name_table = struct.pack(">HHH", 0, 2, string_offset) + rec1 + rec16 + legacy + typo
    offset_table = struct.pack(">IHHHH", 0x00010000, 1, 0, 0, 0)
    directory = struct.pack(">4sIII", b"name", 0, 12 + 16, len(name_table))
    p = tmp_path / "f.ttf"
    p.write_bytes(offset_table + directory + name_table)
    assert read_family_name(p) == "Typographic"


@pytest.fixture
def non_font_file(tmp_path: Path) -> Path:
    p = tmp_path / "notafont.ttf"
    p.write_bytes(b"this is not a font")
    return p


@pytest.fixture
def missing_font_file(tmp_path: Path) -> Path:
    return tmp_path / "ghost.ttf"


@pytest.mark.parametrize("path", [lf("non_font_file"), lf("missing_font_file")])
def test__read_family_name__unreadable_file__returns_none(path: Path) -> None:
    assert read_family_name(path) is None


@pytest.mark.skipif(
    not Path(r"C:\Windows\Fonts\times.ttf").exists(),
    reason="real Times New Roman not present (non-Windows / CI)",
)
def test__read_family_name__real_times_new_roman_font_file__returns_times_new_roman() -> None:
    # Cross-check the parser against a real font when available on the dev box.
    assert read_family_name(Path(r"C:\Windows\Fonts\times.ttf")) == "Times New Roman"
