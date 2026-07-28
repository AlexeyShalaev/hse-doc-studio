from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.fonts.entities import FontCatalog, FontCatalogFile, FontCatalogItem
from hse_doc_studio.infra.fonts.font_store import LocalFontStore
from hse_doc_studio.use_cases.fonts.install_font import InstallFontInput, InstallFontUC
from hse_doc_studio.use_cases.fonts.list_font_catalog import ListFontCatalogUC
from hse_doc_studio.use_cases.fonts.list_fonts import ListFontsUC
from hse_doc_studio.use_cases.fonts.remove_font import RemoveFontInput, RemoveFontUC
from hse_doc_studio.use_cases.fonts.upload_font import UploadFontInput, UploadFontUC

pytestmark = pytest.mark.unit


class _FakeDownloader:
    def __init__(self, mapping: dict[str, bytes]) -> None:
        self._mapping = mapping
        self.calls: list[str] = []

    async def download(self, url: str) -> bytes:
        self.calls.append(url)
        return self._mapping[url]


def _catalog() -> FontCatalog:
    return FontCatalog(
        items=(
            FontCatalogItem(
                id="pt-serif",
                label="PT Serif",
                family="serif",
                description="",
                license="OFL-1.1",
                files=(
                    FontCatalogFile(filename="PTSerif-Regular.ttf", url="https://x/reg.ttf"),
                    FontCatalogFile(filename="PTSerif-Bold.ttf", url="https://x/bold.ttf"),
                ),
            ),
        )
    )


async def test__list_fonts_uc__execute__returns_stored_fonts(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    store.save_font("a.ttf", b"x")
    out = await ListFontsUC(store).execute()
    assert [f.name for f in out.fonts] == ["a.ttf"]


async def test__upload_font_uc__execute__saves_font_and_returns_it(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    out = await UploadFontUC(store).execute(UploadFontInput(filename="times.ttf", content=b"DATA"))
    assert out.font.name == "times.ttf"
    assert store.has_fonts() is True


async def test__upload_font_uc__execute_empty_content__raises_value_error(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    with pytest.raises(ValueError, match="пустой файл шрифта"):
        await UploadFontUC(store).execute(UploadFontInput(filename="times.ttf", content=b""))


async def test__remove_font_uc__execute_missing_font__raises_not_found_error(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    with pytest.raises(NotFoundError, match="шрифт не найден"):
        await RemoveFontUC(store).execute(RemoveFontInput(name="ghost.ttf"))


async def test__list_font_catalog_uc__execute__installed_flag_true_only_when_all_files_present(
    tmp_path: Path,
) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    uc = ListFontCatalogUC(_catalog(), store)
    # Nothing installed yet.
    out = await uc.execute()
    assert out.items[0].installed is False
    assert out.items[0].file_count == 2
    # Only one of the two files present -> still not "installed".
    store.save_font("PTSerif-Regular.ttf", b"x")
    assert (await uc.execute()).items[0].installed is False
    # Both present -> installed.
    store.save_font("PTSerif-Bold.ttf", b"x")
    assert (await uc.execute()).items[0].installed is True


async def test__install_font_uc__execute__downloads_and_saves_all_catalog_files(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    downloader = _FakeDownloader({"https://x/reg.ttf": b"R", "https://x/bold.ttf": b"B"})
    out = await InstallFontUC(_catalog(), downloader, store).execute(InstallFontInput(id="pt-serif"))
    assert {f.name for f in out.installed} == {"PTSerif-Regular.ttf", "PTSerif-Bold.ttf"}
    assert sorted(downloader.calls) == ["https://x/bold.ttf", "https://x/reg.ttf"]
    assert {f.name for f in store.list_fonts()} == {"PTSerif-Regular.ttf", "PTSerif-Bold.ttf"}


async def test__install_font_uc__execute_unknown_catalog_id__raises_not_found_error(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    downloader = _FakeDownloader({})
    with pytest.raises(NotFoundError, match="неизвестный шрифт каталога"):
        await InstallFontUC(_catalog(), downloader, store).execute(InstallFontInput(id="nope"))
