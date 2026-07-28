from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.fonts import system_fonts
from hse_doc_studio.infra.fonts.system_fonts import OsSystemFontProvider
from pytest_lazy_fixtures import lf

pytestmark = pytest.mark.unit


@pytest.fixture
def fake_system_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    sysdir = tmp_path / "sysfonts"
    sub = sysdir / "truetype"
    sub.mkdir(parents=True)
    (sub / "times.ttf").write_bytes(b"TIMES")
    (sysdir / "arial.otf").write_bytes(b"ARIAL")
    (sysdir / "notes.txt").write_text("not a font", encoding="utf-8")
    monkeypatch.setattr(system_fonts, "_candidate_dirs", lambda: [sysdir])
    return sysdir


async def test__os_system_font_provider__list_fonts__finds_only_font_files_recursively(fake_system_dir: Path) -> None:
    names = {f.name for f in await OsSystemFontProvider().list_fonts()}
    assert names == {"times.ttf", "arial.otf"}  # notes.txt excluded


async def test__os_system_font_provider__read_font__returns_bytes(fake_system_dir: Path) -> None:
    provider = OsSystemFontProvider()
    data = await provider.read_font(str(fake_system_dir / "truetype" / "times.ttf"))
    assert data == b"TIMES"


@pytest.fixture
def path_outside_system_dirs(tmp_path: Path) -> str:
    evil = tmp_path / "evil.ttf"
    evil.write_bytes(b"x")
    return str(evil)


@pytest.fixture
def non_font_extension_path(fake_system_dir: Path) -> str:
    return str(fake_system_dir / "notes.txt")


@pytest.fixture
def traversal_escape_path(fake_system_dir: Path, tmp_path: Path) -> str:
    # A '..' that escapes the system dir resolves outside the allowed roots.
    (tmp_path / "escape.ttf").write_bytes(b"x")
    return str(fake_system_dir / ".." / "escape.ttf")


@pytest.mark.parametrize(
    ("bad_path", "match"),
    [
        pytest.param(
            lf("path_outside_system_dirs"), "not inside a known system font directory", id="outside_system_dirs"
        ),
        pytest.param(lf("non_font_extension_path"), "not a font file", id="non_font_extension"),
        pytest.param(lf("traversal_escape_path"), "not inside a known system font directory", id="traversal_escape"),
    ],
)
async def test__os_system_font_provider__read_font_invalid_path__raises_value_error(
    fake_system_dir: Path, bad_path: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        await OsSystemFontProvider().read_font(bad_path)
