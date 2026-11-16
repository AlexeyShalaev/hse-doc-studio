"""Строгий режим рендера (`strict=True`, режим resolve): ошибка Jinja поднимается, сборка копирует как есть."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from hse_doc_studio.infra.project_init.template_renderer import TemplateRenderer, TemplateRenderError, _render_text
from jinja2 import TemplateSyntaxError

_BROKEN = "до ((* if *)) после"
_ATTACK = "{{ cycler.__init__.__globals__.os.popen('echo pwned').read() }}"


def test__render_text__build_mode__broken_template_is_copied_as_is() -> None:
    assert _render_text(_BROKEN, {}, Path("a.tex")) == _BROKEN


def test__render_text__strict__syntax_error_is_raised_with_path_and_cause() -> None:
    with pytest.raises(TemplateRenderError) as caught:
        _render_text(_BROKEN, {}, Path("a.tex"), strict=True)

    assert caught.value.source_path == Path("a.tex")
    assert isinstance(caught.value.cause, TemplateSyntaxError)
    assert "a.tex" in str(caught.value)


def test__render_text__strict__sandbox_violation_is_raised() -> None:
    with pytest.raises(TemplateRenderError):
        _render_text(_ATTACK, {}, Path("evil.tex"), strict=True)


def test__render_text__strict__valid_template_renders_as_usual() -> None:
    assert _render_text("{{ a }}", {"a": "x"}, Path("a.tex"), strict=True) == "x"


def test__render_and_copy__build_mode__broken_file_lands_in_project_unrendered(tmp_path: Path) -> None:
    source, dest = tmp_path / "files", tmp_path / "dest"
    source.mkdir()
    dest.mkdir()
    (source / "main.tex").write_text(_BROKEN, encoding="utf-8")

    written = TemplateRenderer().render_and_copy(source, dest, {})

    assert written == ["main.tex"]
    assert (dest / "main.tex").read_text(encoding="utf-8") == _BROKEN


def test__render_and_copy__strict__broken_file_raises_instead_of_a_silent_copy(tmp_path: Path) -> None:
    source, dest = tmp_path / "files", tmp_path / "dest"
    source.mkdir()
    dest.mkdir()
    (source / "main.tex").write_text(_BROKEN, encoding="utf-8")

    with pytest.raises(TemplateRenderError):
        TemplateRenderer().render_and_copy(source, dest, {}, strict=True)


def _pptx(path: Path, slide: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", slide)


def test__render_and_copy__pptx_slide__build_mode_copies_strict_mode_raises(tmp_path: Path) -> None:
    source, dest = tmp_path / "files", tmp_path / "dest"
    source.mkdir()
    dest.mkdir()
    _pptx(source / "pres.pptx", "<a>((* if *))</a>")

    TemplateRenderer().render_and_copy(source, dest, {})
    with zipfile.ZipFile(dest / "pres.pptx") as archive:
        assert archive.read("ppt/slides/slide1.xml") == b"<a>((* if *))</a>"

    with pytest.raises(TemplateRenderError):
        TemplateRenderer().render_and_copy(source, dest, {}, strict=True)
