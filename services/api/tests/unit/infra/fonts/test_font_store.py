from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.fonts.font_store import LocalFontStore


@pytest.mark.unit
def test__local_font_store__save_font__saved_font_appears_in_list_and_on_disk(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    saved = store.save_font("times.ttf", b"FONTDATA")
    assert saved.name == "times.ttf"
    assert saved.size_bytes == len(b"FONTDATA")
    listed = store.list_fonts()
    assert [f.name for f in listed] == ["times.ttf"]
    assert (tmp_path / "fonts" / "times.ttf").read_bytes() == b"FONTDATA"


@pytest.mark.unit
def test__local_font_store__save_font_non_font_extension__raises_value_error(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    with pytest.raises(ValueError, match="unsupported font file"):
        store.save_font("malware.exe", b"x")


@pytest.mark.unit
def test__local_font_store__save_font_path_traversal__strips_to_basename(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    saved = store.save_font("../../evil.ttf", b"x")
    # Only the basename is used, so nothing escapes the fonts dir.
    assert saved.name == "evil.ttf"
    assert (tmp_path / "fonts" / "evil.ttf").exists()
    assert not (tmp_path / "evil.ttf").exists()


@pytest.mark.unit
def test__local_font_store__list_fonts__ignores_non_font_files(tmp_path: Path) -> None:
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "readme.txt").write_text("nope", encoding="utf-8")
    (fonts / "arial.otf").write_bytes(b"x")
    assert [f.name for f in LocalFontStore(fonts).list_fonts()] == ["arial.otf"]


@pytest.mark.unit
def test__local_font_store__delete_font__removes_it_and_reports_false_when_already_gone(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    store.save_font("a.ttf", b"x")
    assert store.delete_font("a.ttf") is True
    assert store.delete_font("a.ttf") is False  # already gone
    assert store.list_fonts() == []


@pytest.mark.unit
def test__local_font_store__has_fonts__reflects_whether_any_font_is_saved(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    assert store.has_fonts() is False  # dir doesn't exist yet
    store.save_font("a.ttf", b"x")
    assert store.has_fonts() is True


@pytest.mark.unit
def test__local_font_store__read_font__returns_bytes(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    store.save_font("a.ttf", b"FONTDATA")
    assert store.read_font("a.ttf") == b"FONTDATA"


@pytest.mark.unit
def test__local_font_store__read_font_missing_file_or_non_font_extension__returns_none(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    assert store.read_font("ghost.ttf") is None
    # A non-font extension is never served, even if such a file somehow exists.
    assert store.read_font("notes.txt") is None


@pytest.mark.unit
def test__local_font_store__read_font_path_traversal__returns_none(tmp_path: Path) -> None:
    store = LocalFontStore(tmp_path / "fonts")
    store.save_font("a.ttf", b"FONTDATA")
    secret = tmp_path / "secret.ttf"
    secret.write_bytes(b"SECRET")
    # Only the basename is honoured, so a crafted path can't escape the folder.
    assert store.read_font("../secret.ttf") is None
