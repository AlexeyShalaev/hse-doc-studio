from __future__ import annotations

import json
import tarfile
import zipfile
from datetime import date
from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import (
    ChecksVersionConfig,
    DocumentDefinition,
    DocumentVariant,
    EngineConfig,
    ExtraSubmissionItem,
    PackSubmissionConfig,
    SignaturesConfig,
    SubmissionDocItem,
    TemplateVersion,
)
from hse_doc_studio.core.enums import EngineType, TemplateVersionStatus
from hse_doc_studio.core.value_objects import ChecksOverride, SignaturePlacement, SignatureSlot, SignaturesState
from hse_doc_studio.infra.submission.assembler import (
    SubmissionAssembler,
    archive_ext,
    available_archive_formats,
    is_archive_format_available,
)
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.submission.create_submission import _form_id_for_extra

from tests.factories import make_custom_file_override, make_document, make_project, make_template_version

# parents[0]=submission, [1]=infra, [2]=unit, [3]=tests, [4]=service-root, [5]=services, [6]=monorepo
_PACKS_DIR = Path(__file__).resolve().parents[6] / "packs"

_AI_SOURCE = ".hse-studio/forms/ai_declaration.json"


def _ai_extra() -> ExtraSubmissionItem:
    return ExtraSubmissionItem(source=_AI_SOURCE, output_name="Декларация ИИ.md", format="markdown")


def _make_template_version(documents: tuple[DocumentDefinition, ...]) -> TemplateVersion:
    return TemplateVersion(
        pack_id="hse-cs-se",
        template_id="vkr",
        version="1.0",
        status=TemplateVersionStatus.stable,
        released_at=date(2026, 1, 1),
        summary={"ru": "Test version"},
        engine_config=EngineConfig(
            default=EngineType.xelatex,
            allowed=(EngineType.xelatex,),
            passes=2,
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


def _make_document_definition(doc_id: str, output_file: str, output_name: dict[str, str]) -> DocumentDefinition:
    return DocumentDefinition(
        id=doc_id,
        name={"ru": doc_id},
        code={"ru": doc_id.upper()},
        source_file=f"{doc_id}/main.tex",
        output_file=output_file,
        output_name=output_name,
        gost_ref=None,
        required=True,
        checks=ChecksOverride(),
        variants=(),
    )


def _empty_sig_state() -> SignaturesState:
    return SignaturesState(slots={}, placements={})


async def test__populate_dir__doc_item_present__folder_contains_named_pdf(tmp_path: Path) -> None:
    doc_id = "tz"
    output_file = f"{doc_id}/main.pdf"
    output_name_ru = "ТЗ.pdf"
    doc_def = _make_document_definition(doc_id, output_file, {"ru": output_name_ru})
    template_version = _make_template_version(documents=(doc_def,))

    project_folder = tmp_path / "my-project"
    pdf_path = project_folder / output_file
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.4 dummy content")

    output_dir = tmp_path / "submissions" / "final-20260101T000000"
    assembler = SubmissionAssembler()

    written = await assembler.populate_dir(
        output_dir=output_dir,
        project_folder=project_folder,
        doc_items=[SubmissionDocItem(doc_id=doc_id, signatures=())],
        extra_items=[],
        template_version=template_version,
        signatures_state=_empty_sig_state(),
        lang="ru",
    )

    assert written == [output_name_ru]
    assert (output_dir / output_name_ru).exists()


async def test__populate_dir__variant_doc__uses_variant_output_name(tmp_path: Path) -> None:
    # Вариантный док (def-level output_name пуст, как у pres в паке):
    # имя в пакете должно прийти из ВЫБРАННОГО варианта, а не деградировать в путь
    pptx_variant = DocumentVariant(
        id="pptx",
        label={"ru": "PowerPoint"},
        source_file="pres/pptx/presentation.pptx",
        output_file="pres/pptx/presentation.pptx",
        output_name={"ru": "Презентация.pptx"},
        engine=None,
    )
    beamer_variant = DocumentVariant(
        id="beamer",
        label={"ru": "Beamer"},
        source_file="pres/beamer/pres.tex",
        output_file="pres/beamer/pres.pdf",
        output_name={"ru": "Презентация.pdf"},
        engine=EngineType.xelatex,
    )
    doc_def = DocumentDefinition(
        id="pres",
        name={"ru": "Презентация"},
        code={"ru": "PRES"},
        source_file=None,
        output_file=None,
        output_name={},
        gost_ref=None,
        required=False,
        checks=ChecksOverride(),
        variants=(pptx_variant, beamer_variant),
    )
    template_version = _make_template_version(documents=(doc_def,))
    project = make_project(documents=[make_document("pres", chosen_variant="pptx")])

    project_folder = tmp_path / "my-project"
    src = project_folder / "pres" / "pptx" / "presentation.pptx"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"PK fake pptx")

    output_dir = tmp_path / "submissions" / "final"
    assembler = SubmissionAssembler()

    written = await assembler.populate_dir(
        output_dir=output_dir,
        project_folder=project_folder,
        doc_items=[SubmissionDocItem(doc_id="pres", signatures=())],
        extra_items=[],
        template_version=template_version,
        signatures_state=_empty_sig_state(),
        lang="ru",
        project=project,
    )

    # arcname взят из output_name варианта pptx
    assert written == ["Презентация.pptx"]
    assert (output_dir / "Презентация.pptx").read_bytes() == b"PK fake pptx"


async def test__populate_dir__raw_extra_present__folder_contains_extra(tmp_path: Path) -> None:
    template_version = _make_template_version(documents=())
    project_folder = tmp_path / "my-project"
    project_folder.mkdir(parents=True)
    (project_folder / "readme.txt").write_text("extra content", encoding="utf-8")

    output_dir = tmp_path / "submissions" / "final"
    assembler = SubmissionAssembler()

    written = await assembler.populate_dir(
        output_dir=output_dir,
        project_folder=project_folder,
        doc_items=[],
        extra_items=[ExtraSubmissionItem(source="readme.txt", output_name="README.txt", format=None)],
        template_version=template_version,
        signatures_state=_empty_sig_state(),
        lang="ru",
    )

    assert written == ["README.txt"]
    assert (output_dir / "README.txt").read_text(encoding="utf-8") == "extra content"


async def test__populate_dir__missing_pdf__doc_item_skipped_gracefully(tmp_path: Path) -> None:
    # Compiled PDF does NOT exist; assembler must not crash
    doc_def = _make_document_definition("vkr", "vkr/main.pdf", {"ru": "ВКР.pdf"})
    template_version = _make_template_version(documents=(doc_def,))
    project_folder = tmp_path / "my-project"
    project_folder.mkdir(parents=True)

    output_dir = tmp_path / "submissions" / "final"
    assembler = SubmissionAssembler()

    written = await assembler.populate_dir(
        output_dir=output_dir,
        project_folder=project_folder,
        doc_items=[SubmissionDocItem(doc_id="vkr", signatures=())],
        extra_items=[],
        template_version=template_version,
        signatures_state=_empty_sig_state(),
        lang="ru",
    )

    # Folder created but empty (missing PDF skipped)
    assert written == []
    assert output_dir.exists()
    assert list(output_dir.iterdir()) == []


async def test__populate_dir__extra_output_name_escapes__skipped_no_write_outside(tmp_path: Path) -> None:
    # A crafted output_name tries to escape the submission folder
    template_version = _make_template_version(documents=())
    project_folder = tmp_path / "my-project"
    project_folder.mkdir(parents=True)
    (project_folder / "readme.txt").write_text("x", encoding="utf-8")
    output_dir = tmp_path / "submissions" / "final"
    escape_target = tmp_path / "submissions" / "evil.txt"  # one level above output_dir
    assembler = SubmissionAssembler()

    written = await assembler.populate_dir(
        output_dir=output_dir,
        project_folder=project_folder,
        doc_items=[],
        extra_items=[ExtraSubmissionItem(source="readme.txt", output_name="../evil.txt", format=None)],
        template_version=template_version,
        signatures_state=_empty_sig_state(),
        lang="ru",
    )

    # Refused, nothing written outside output_dir
    assert written == []
    assert not escape_target.exists()


async def test__populate_dir__extra_source_escapes__skipped(tmp_path: Path) -> None:
    # A secret outside the project must not be readable via "../"
    template_version = _make_template_version(documents=())
    project_folder = tmp_path / "my-project"
    project_folder.mkdir(parents=True)
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    output_dir = tmp_path / "submissions" / "final"
    assembler = SubmissionAssembler()

    written = await assembler.populate_dir(
        output_dir=output_dir,
        project_folder=project_folder,
        doc_items=[],
        extra_items=[ExtraSubmissionItem(source="../secret.txt", output_name="leaked.txt", format=None)],
        template_version=template_version,
        signatures_state=_empty_sig_state(),
        lang="ru",
    )

    # Refused, secret not copied into the submission folder
    assert written == []
    assert not (output_dir / "leaked.txt").exists()


def test__create_archive__zip__contains_folder_contents_flat(tmp_path: Path) -> None:
    src_dir = tmp_path / "submissions" / "final"
    src_dir.mkdir(parents=True)
    (src_dir / "ТЗ.pdf").write_bytes(b"%PDF-1.4 a")
    (src_dir / "ВКР.pdf").write_bytes(b"%PDF-1.4 b")
    assembler = SubmissionAssembler()

    archive = assembler.create_archive(src_dir, tmp_path / "submissions" / "final", "zip")

    assert archive.name == "final.zip"
    with zipfile.ZipFile(archive, "r") as zf:
        assert sorted(zf.namelist()) == ["ВКР.pdf", "ТЗ.pdf"]


def test__create_archive__targz__produces_tar_gz(tmp_path: Path) -> None:
    src_dir = tmp_path / "submissions" / "final"
    src_dir.mkdir(parents=True)
    (src_dir / "doc.pdf").write_bytes(b"%PDF-1.4 a")
    assembler = SubmissionAssembler()

    archive = assembler.create_archive(src_dir, tmp_path / "submissions" / "final", "targz")

    assert archive.name == "final.tar.gz"
    with tarfile.open(archive, "r:gz") as tf:
        # gztar prefixes entries with "./"; match by basename.
        assert any(name.rsplit("/", 1)[-1] == "doc.pdf" for name in tf.getnames())


def test__create_archive__unknown_format__raises(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    assembler = SubmissionAssembler()
    with pytest.raises(ValueError, match="Unknown archive format"):
        assembler.create_archive(src_dir, tmp_path / "out", "bogus")


def test__archive_format_catalog__native_always_available(monkeypatch: pytest.MonkeyPatch) -> None:
    # External-tool formats (7z/rar) probe the real PATH via shutil.which — pin it
    # deterministically so this test never depends on what's installed on the host.
    monkeypatch.setattr("hse_doc_studio.infra.submission.assembler.shutil.which", lambda _tool: None)

    assert is_archive_format_available("zip") is True
    assert is_archive_format_available("targz") is True
    assert is_archive_format_available("bogus") is False
    assert archive_ext("zip") == ".zip"
    assert archive_ext("targz") == ".tar.gz"

    catalog = {f["id"]: f for f in available_archive_formats()}
    assert set(catalog) == {"zip", "targz", "7z", "rar"}
    assert catalog["zip"]["available"] is True
    assert catalog["7z"]["available"] is False


# ──────────────────────────────────────────────────────────────────────────
# _resolve_doc_target — custom_file branches
# ──────────────────────────────────────────────────────────────────────────


async def test__populate_dir__custom_file_already_pdf__used_as_is_signable(tmp_path: Path) -> None:
    # custom_file is itself a PDF: no decision needed, is_pdf=True.
    doc_def = _make_document_definition("tz", "tz/tz.pdf", {"ru": "ТЗ.pdf"})
    template_version = _make_template_version(documents=(doc_def,))
    custom = make_custom_file_override(original_filename="my-tz.pdf", stored_path="tz/_custom/my-tz.pdf", ext=".pdf")
    project = make_project(documents=[make_document("tz", custom_file=custom)])

    project_folder = tmp_path / "my-project"
    src = project_folder / "tz" / "_custom" / "my-tz.pdf"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"%PDF-1.4 custom")

    output_dir = tmp_path / "submissions" / "final"
    assembler = SubmissionAssembler()

    written = await assembler.populate_dir(
        output_dir=output_dir,
        project_folder=project_folder,
        doc_items=[SubmissionDocItem(doc_id="tz", signatures=())],
        extra_items=[],
        template_version=template_version,
        signatures_state=_empty_sig_state(),
        lang="ru",
        project=project,
    )

    # The stored PDF is included verbatim under a .pdf name
    assert len(written) == 1
    assert written[0].lower().endswith(".pdf")
    assert (output_dir / written[0]).read_bytes() == b"%PDF-1.4 custom"


async def test__populate_dir__custom_file_convertible_decision_true__uses_sibling_preview(tmp_path: Path) -> None:
    # Convertible office format, decision=True, sibling preview PDF
    # already exists on disk (generated at upload time) — used directly, no
    # OfficeConvertManager call needed.
    doc_def = _make_document_definition("tz", "tz/tz.tex", {"ru": "ТЗ.pdf"})
    template_version = _make_template_version(documents=(doc_def,))
    custom = make_custom_file_override(original_filename="ТЗ.docx", stored_path="tz/_custom/ТЗ.docx", ext=".docx")
    project = make_project(documents=[make_document("tz", custom_file=custom)])

    project_folder = tmp_path / "my-project"
    custom_dir = project_folder / "tz" / "_custom"
    custom_dir.mkdir(parents=True)
    (custom_dir / "ТЗ.docx").write_bytes(b"fake docx bytes")
    (custom_dir / "ТЗ.pdf").write_bytes(b"%PDF-1.4 preview")

    output_dir = tmp_path / "submissions" / "final"
    assembler = SubmissionAssembler()  # no office_manager needed: preview already on disk

    written = await assembler.populate_dir(
        output_dir=output_dir,
        project_folder=project_folder,
        doc_items=[SubmissionDocItem(doc_id="tz", signatures=())],
        extra_items=[],
        template_version=template_version,
        signatures_state=_empty_sig_state(),
        lang="ru",
        project=project,
        custom_doc_decisions={"tz": True},
    )

    # Sibling preview PDF is what got packaged
    assert len(written) == 1
    assert written[0].lower().endswith(".pdf")
    assert (output_dir / written[0]).read_bytes() == b"%PDF-1.4 preview"


async def test__populate_dir__custom_file_declined_or_unknown__raw_file_included_unstamped(tmp_path: Path) -> None:
    # decision=False (or absent): raw file included as-is under its
    # real extension, never fed to the PDF stamper.
    doc_def = _make_document_definition("tz", "tz/tz.tex", {"ru": "ТЗ.pdf"})
    template_version = _make_template_version(documents=(doc_def,))
    custom = make_custom_file_override(original_filename="ТЗ.docx", stored_path="tz/_custom/ТЗ.docx", ext=".docx")
    project = make_project(documents=[make_document("tz", custom_file=custom)])

    project_folder = tmp_path / "my-project"
    custom_dir = project_folder / "tz" / "_custom"
    custom_dir.mkdir(parents=True)
    (custom_dir / "ТЗ.docx").write_bytes(b"fake docx bytes")

    output_dir = tmp_path / "submissions" / "final"
    assembler = SubmissionAssembler()

    # No decision provided, and convert_to_pdf_at_package is None
    written = await assembler.populate_dir(
        output_dir=output_dir,
        project_folder=project_folder,
        doc_items=[SubmissionDocItem(doc_id="tz", signatures=())],
        extra_items=[],
        template_version=template_version,
        signatures_state=_empty_sig_state(),
        lang="ru",
        project=project,
    )

    # Raw .docx included as-is, unconverted
    assert len(written) == 1
    assert written[0].lower().endswith(".docx")
    assert (output_dir / written[0]).read_bytes() == b"fake docx bytes"


async def test__populate_dir__custom_file_with_placements__unsignable_file_never_stamped(tmp_path: Path) -> None:
    # A signature placement exists for this doc, but the custom file
    # stays a raw .docx (declined conversion): the stamper must NEVER be
    # invoked on it (that would crash trying to parse a non-PDF as a PDF).
    doc_def = _make_document_definition("tz", "tz/tz.tex", {"ru": "ТЗ.pdf"})
    template_version = _make_template_version(documents=(doc_def,))
    custom = make_custom_file_override(original_filename="ТЗ.docx", stored_path="tz/_custom/ТЗ.docx", ext=".docx")
    project = make_project(documents=[make_document("tz", custom_file=custom)])

    project_folder = tmp_path / "my-project"
    custom_dir = project_folder / "tz" / "_custom"
    custom_dir.mkdir(parents=True)
    (custom_dir / "ТЗ.docx").write_bytes(b"fake docx bytes")

    # A signature slot with an enabled placement + PNG for this doc — if the
    # assembler ignored is_pdf it would try (and crash) to stamp the .docx.
    png_path = project_folder / ".hse-studio" / "signatures" / "author.png"
    png_path.parent.mkdir(parents=True)
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    sig_state = SignaturesState(
        slots={
            "author": SignatureSlot(
                png_path=str(png_path.relative_to(project_folder)),
                natural_width_px=100,
                natural_height_px=40,
            )
        },
        placements={"tz": {"author": SignaturePlacement(enabled=True, page=1, x_mm=10, y_mm=10, width_mm=50)}},
    )

    output_dir = tmp_path / "submissions" / "final"
    assembler = SubmissionAssembler()

    written = await assembler.populate_dir(
        output_dir=output_dir,
        project_folder=project_folder,
        doc_items=[SubmissionDocItem(doc_id="tz", signatures=("author",))],
        extra_items=[],
        template_version=template_version,
        signatures_state=sig_state,
        lang="ru",
        project=project,
    )

    # Copied unstamped (content identical to source, no crash)
    assert len(written) == 1
    assert (output_dir / written[0]).read_bytes() == b"fake docx bytes"


async def test__populate_dir__rendered_extra_present__written_verbatim(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    body = "# Декларация ИИ\n\n| Инструмент |\n| ChatGPT |\n"

    written = await SubmissionAssembler().populate_dir(
        output_dir=out_dir,
        project_folder=tmp_path / "proj",  # need not exist: rendered body wins
        doc_items=[],
        extra_items=[_ai_extra()],
        template_version=make_template_version(),
        signatures_state=SignaturesState.empty(),
        rendered_extras={_AI_SOURCE: body},
    )

    assert "Декларация ИИ.md" in written
    md = out_dir / "Декларация ИИ.md"
    text = md.read_text(encoding="utf-8")
    assert text == body
    # Must NOT be the legacy key/value json dump.
    assert "**schema_version**" not in text
    assert "**answers**" not in text


async def test__populate_dir__no_rendered_extra__falls_back_to_json_dump(tmp_path: Path) -> None:
    project_folder = tmp_path / "proj"
    (project_folder / ".hse-studio" / "forms").mkdir(parents=True)
    (project_folder / ".hse-studio" / "forms" / "ai_declaration.json").write_text(
        json.dumps({"completed": True, "answers": {}}), encoding="utf-8"
    )
    out_dir = tmp_path / "out"

    written = await SubmissionAssembler().populate_dir(
        output_dir=out_dir,
        project_folder=project_folder,
        doc_items=[],
        extra_items=[_ai_extra()],
        template_version=make_template_version(),
        signatures_state=SignaturesState.empty(),
        rendered_extras=None,
    )

    # Legacy behaviour preserved when nothing was pre-rendered
    assert "Декларация ИИ.md" in written
    text = (out_dir / "Декларация ИИ.md").read_text(encoding="utf-8")
    assert "**completed**" in text


def test__form_id_for_extra__maps_form_answers_source_to_form_id() -> None:
    repo = YamlTemplateRepository(_PACKS_DIR)
    repo.load()
    version = repo.get_version("hse-cs-se", "vkr", "2026.1")
    assert version is not None

    assert _form_id_for_extra(_ai_extra(), version) == "ai_declaration"
    # Non-form source → not rendered through a template.
    raw = ExtraSubmissionItem(source="some/other/file.json", output_name="x.md", format="markdown")
    assert _form_id_for_extra(raw, version) is None
    # Wrong format → ignored.
    not_md = ExtraSubmissionItem(source=_AI_SOURCE, output_name="x.txt", format="raw")
    assert _form_id_for_extra(not_md, version) is None
