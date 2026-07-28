from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.fonts.entities import SystemFontFile
from hse_doc_studio.infra.fonts.font_store import LocalFontStore
from hse_doc_studio.use_cases.fonts.import_system_fonts import ImportSystemFontsInput, ImportSystemFontsUC
from hse_doc_studio.use_cases.fonts.list_system_fonts import ListSystemFontsUC

pytestmark = pytest.mark.unit


class _FakeSystemProvider:
    def __init__(self, fonts: list[SystemFontFile], data: dict[str, bytes]) -> None:
        self._fonts = fonts
        self._data = data

    async def list_fonts(self) -> list[SystemFontFile]:
        return list(self._fonts)

    async def read_font(self, path: str) -> bytes:
        if path not in self._data:
            raise ValueError("not inside a known system font directory")
        return self._data[path]


async def test__list_system_fonts_uc__execute__marks_fonts_already_installed(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    store.save_font("times.ttf", b"x")
    provider = _FakeSystemProvider(
        [SystemFontFile("times.ttf", "/sys/times.ttf"), SystemFontFile("arial.ttf", "/sys/arial.ttf")],
        {},
    )
    out = await ListSystemFontsUC(provider, store).execute()
    assert out.available is True
    by_name = {f.name: f.already_installed for f in out.fonts}
    assert by_name == {"times.ttf": True, "arial.ttf": False}


async def test__list_system_fonts_uc__execute_no_system_fonts__reports_unavailable(tmp_path: Path) -> None:
    out = await ListSystemFontsUC(_FakeSystemProvider([], {}), LocalFontStore(tmp_path / "fonts")).execute()
    assert out.available is False
    assert out.fonts == []


async def test__import_system_fonts_uc__execute_selected_paths__copies_them_into_store(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    provider = _FakeSystemProvider(
        [SystemFontFile("times.ttf", "/sys/times.ttf")],
        {"/sys/times.ttf": b"TIMESDATA"},
    )
    out = await ImportSystemFontsUC(provider, store).execute(ImportSystemFontsInput(paths=["/sys/times.ttf"]))
    assert [f.name for f in out.installed] == ["times.ttf"]
    assert {f.name for f in store.list_fonts()} == {"times.ttf"}


async def test__import_system_fonts_uc__execute_empty_paths__raises_value_error(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    with pytest.raises(ValueError, match="шрифты не выбраны"):
        await ImportSystemFontsUC(_FakeSystemProvider([], {}), store).execute(ImportSystemFontsInput(paths=[]))


async def test__import_system_fonts_uc__execute_path_provider_rejects__propagates_value_error(
    tmp_path: Path,
) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    provider = _FakeSystemProvider([], {})  # read_font raises for any path
    with pytest.raises(ValueError, match="not inside a known system font directory"):
        await ImportSystemFontsUC(provider, store).execute(ImportSystemFontsInput(paths=["/etc/passwd.ttf"]))
