from __future__ import annotations

import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from hse_doc_studio.core.catalog import (
    ChecksVersionConfig,
    DocumentDefinition,
    DocumentVariant,
    EngineConfig,
    PackInfo,
    PackSubmissionConfig,
    SignaturesConfig,
    TemplateInfo,
    TemplateVersion,
)
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import (
    EngineType,
    Lang,
    ProjectKind,
    ProjectStaffing,
    TemplateVersionStatus,
)
from hse_doc_studio.core.value_objects import Author, ChecksOverride, ProjectLock
from hse_doc_studio.infra.project_init.template_renderer import (
    TemplateRenderer,
    build_context,
)


def _make_project(folder: Path, author_name: str = "Иванов И.И.") -> Project:
    return Project(
        id=uuid4(),
        name="Тестовый проект",
        folder=folder,
        lock=ProjectLock(
            pack_id="test-pack",
            template_id="test-tmpl",
            version="1.0",
            engine=EngineType.xelatex,
        ),
        kind=ProjectKind.research,
        staffing=ProjectStaffing.solo,
        lang=Lang.ru,
        authors=[Author(name=author_name, group="БПИ201")],
        meta={"title": "Test"},
        supervisor=None,
        co_supervisor=None,
        documents=[],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_pack_info() -> PackInfo:
    return PackInfo(
        id="test-pack",
        name={"ru": "Test"},
        description={"ru": ""},
        maintainer={"name": "Test"},
        license="MIT",
        templates=(),
    )


def _make_template_info() -> TemplateInfo:
    return TemplateInfo(
        pack_id="test-pack",
        id="test-tmpl",
        name={"ru": "Test Template"},
        short_name={"ru": "Test"},
        description={"ru": ""},
        icon="",
        accent_hue=0,
        default_version="1.0",
    )


def _make_version(documents: tuple[DocumentDefinition, ...] = ()) -> TemplateVersion:
    return TemplateVersion(
        pack_id="test-pack",
        template_id="test-tmpl",
        version="1.0",
        status=TemplateVersionStatus.stable,
        released_at=date(2026, 1, 1),
        summary={"ru": "Test"},
        engine_config=EngineConfig(
            default=EngineType.xelatex,
            allowed=(EngineType.xelatex,),
            passes=1,
            flags="",
        ),
        required_tex_packages=(),
        documents=documents,
        meta_fields={},
        signatures_config=SignaturesConfig(slots=()),
        pack_submission=PackSubmissionConfig(profiles=()),
        checks_config=ChecksVersionConfig(disabled_categories=(), disabled=(), severity_override={}),
        rules=(),
    )


def test__build_context__project_fields__present_in_context(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    ctx = build_context(project, _make_pack_info(), _make_template_info(), _make_version())
    assert ctx["project"]["name"] == "Тестовый проект"
    assert ctx["project"]["meta"] == {"title": "Test"}
    assert ctx["pack"]["id"] == "test-pack"
    assert ctx["template"]["id"] == "test-tmpl"
    assert ctx["template"]["version"] == "1.0"


def test__render__jinja2_template__substitutes_placeholders(tmp_path: Path) -> None:
    version_dir = tmp_path / "version_files"
    dest_dir = tmp_path / "dest"
    version_dir.mkdir()
    dest_dir.mkdir()

    (version_dir / "tz").mkdir()
    (version_dir / "tz" / "tz.tex").write_text("\\title{{ '{' }}{{ project.name }}{{ '}' }}", encoding="utf-8")
    # Simpler: just write a plain Jinja expression in a .tex file
    (version_dir / "main.tex").write_text("{{ project.name }}", encoding="utf-8")

    project = _make_project(tmp_path)
    ctx = build_context(project, _make_pack_info(), _make_template_info(), _make_version())

    renderer = TemplateRenderer()
    renderer.render_and_copy(version_dir, dest_dir, ctx)

    rendered = (dest_dir / "main.tex").read_text(encoding="utf-8")
    assert "Тестовый проект" in rendered


def test__render__non_template_file__copied_verbatim(tmp_path: Path) -> None:
    version_dir = tmp_path / "version_files"
    dest_dir = tmp_path / "dest"
    version_dir.mkdir()
    dest_dir.mkdir()

    # .gitkeep has no known extension — copied as-is (unknown extension path)
    binary_data = b"\x00\x01\x02\x03"
    (version_dir / "image.png").write_bytes(binary_data)

    project = _make_project(tmp_path)
    ctx = build_context(project, _make_pack_info(), _make_template_info(), _make_version())

    renderer = TemplateRenderer()
    renderer.render_and_copy(version_dir, dest_dir, ctx)

    assert (dest_dir / "image.png").read_bytes() == binary_data


def test__render__document_with_variants__copies_all_variant_files(tmp_path: Path) -> None:
    # Смена варианта — lossless: при создании копируются каталоги ВСЕХ
    # вариантов, независимо от того, какой выбран в инстансе документа.
    version_dir = tmp_path / "version_files"
    dest_dir = tmp_path / "dest"
    version_dir.mkdir()
    dest_dir.mkdir()

    # Create two variant directories for a "pres" document
    (version_dir / "pres" / "pptx").mkdir(parents=True)
    (version_dir / "pres" / "reveal").mkdir(parents=True)
    (version_dir / "pres" / "pptx" / "slides.pptx").write_bytes(b"pptx-content")
    (version_dir / "pres" / "reveal" / "index.html").write_text("<html></html>", encoding="utf-8")

    pptx_variant = DocumentVariant(
        id="pptx",
        label={"ru": "PowerPoint"},
        source_file="pres/pptx/slides.pptx",
        output_file="slides.pptx",
        output_name={"ru": "Презентация"},
        engine=None,
    )
    reveal_variant = DocumentVariant(
        id="reveal",
        label={"ru": "Reveal.js"},
        source_file="pres/reveal/index.html",
        output_file="index.html",
        output_name={"ru": "Презентация"},
        engine=None,
    )
    doc_def = DocumentDefinition(
        id="pres",
        name={"ru": "Презентация"},
        code={"ru": "PRES"},
        source_file=None,
        output_file=None,
        output_name={"ru": "Презентация"},
        gost_ref=None,
        required=False,
        checks=ChecksOverride(),
        variants=(pptx_variant, reveal_variant),
    )
    version = _make_version(documents=(doc_def,))

    project = _make_project(tmp_path)
    ctx = build_context(project, _make_pack_info(), _make_template_info(), version)

    renderer = TemplateRenderer()
    renderer.render_and_copy(version_dir, dest_dir, ctx)

    assert (dest_dir / "pres" / "pptx" / "slides.pptx").exists()
    assert (dest_dir / "pres" / "reveal" / "index.html").exists()


def test__render__skip_existing__preserves_user_edits_and_fills_missing_files(tmp_path: Path) -> None:
    # skip_existing=True: существующий (правленный студентом) файл не
    # перезаписывается, отсутствующие докладываются; возвращаются rel-пути
    # реально записанных файлов.
    version_dir = tmp_path / "version_files"
    dest_dir = tmp_path / "dest"
    version_dir.mkdir()
    dest_dir.mkdir()

    (version_dir / "tz").mkdir()
    (version_dir / "tz" / "tz.tex").write_text("pack content", encoding="utf-8")
    (version_dir / "tz" / "extra.tex").write_text("{{ project.name }}", encoding="utf-8")

    (dest_dir / "tz").mkdir()
    (dest_dir / "tz" / "tz.tex").write_text("edited by student", encoding="utf-8")

    project = _make_project(tmp_path)
    ctx = build_context(project, _make_pack_info(), _make_template_info(), _make_version())

    renderer = TemplateRenderer()
    created = renderer.render_and_copy(version_dir, dest_dir, ctx, skip_existing=True)

    assert created == ["tz/extra.tex"]
    assert (dest_dir / "tz" / "tz.tex").read_text(encoding="utf-8") == "edited by student"
    assert (dest_dir / "tz" / "extra.tex").read_text(encoding="utf-8") == "Тестовый проект"


def test__render__pptx_template__slides_substituted_other_members_intact(tmp_path: Path) -> None:
    version_dir = tmp_path / "version_files"
    dest_dir = tmp_path / "dest"
    version_dir.mkdir()
    dest_dir.mkdir()

    # Минимальный pptx: слайд с Jinja-плейсхолдером + бинарный член + «чистый» XML
    binary_member = b"\x00\x01\x02\xff"
    src_pptx = version_dir / "presentation.pptx"
    with zipfile.ZipFile(src_pptx, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("ppt/slides/slide1.xml", "<a:t>{{ author.name | xmlesc }}</a:t>")
        zf.writestr("ppt/media/image1.bin", binary_member)

    # Имя автора с XML-спецсимволами — xmlesc обязан их экранировать
    project = _make_project(tmp_path, author_name="Иванов & <Ко>")
    ctx = build_context(project, _make_pack_info(), _make_template_info(), _make_version())

    renderer = TemplateRenderer()
    renderer.render_and_copy(version_dir, dest_dir, ctx)

    with zipfile.ZipFile(dest_dir / "presentation.pptx", "r") as zf:
        # Порядок членов сохранён
        assert zf.namelist() == ["[Content_Types].xml", "ppt/slides/slide1.xml", "ppt/media/image1.bin"]
        # Слайд отрендерен с экранированием XML
        assert zf.read("ppt/slides/slide1.xml").decode("utf-8") == "<a:t>Иванов &amp; &lt;Ко&gt;</a:t>"
        # Остальные члены — байт-в-байт
        assert zf.read("[Content_Types].xml") == b"<Types/>"
        assert zf.read("ppt/media/image1.bin") == binary_member


def test__render__pptx_corrupt_zip__falls_back_to_verbatim_copy(tmp_path: Path) -> None:
    version_dir = tmp_path / "version_files"
    dest_dir = tmp_path / "dest"
    version_dir.mkdir()
    dest_dir.mkdir()

    # Не zip вовсе — рендер должен молча упасть в copy2, а не сорвать копирование
    corrupt = b"definitely not a zip archive"
    (version_dir / "broken.pptx").write_bytes(corrupt)

    project = _make_project(tmp_path)
    ctx = build_context(project, _make_pack_info(), _make_template_info(), _make_version())

    renderer = TemplateRenderer()
    renderer.render_and_copy(version_dir, dest_dir, ctx)

    assert (dest_dir / "broken.pptx").read_bytes() == corrupt
