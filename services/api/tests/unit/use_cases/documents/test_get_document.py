from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.documents.get_document import GetDocumentInput, GetDocumentUC

from tests.factories import (
    make_custom_file_override,
    make_document,
    make_document_definition,
    make_project,
    make_template_version,
)


def _make_uc(project: Project, documents: tuple = ()) -> GetDocumentUC:
    template_repo = MagicMock()
    template_repo.get_version.return_value = make_template_version(documents=documents)
    uc = GetDocumentUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        template_repo=template_repo,
    )
    uc._get_uc = AsyncMock()
    uc._get_uc.execute.return_value = SimpleNamespace(project=project)
    return uc


def _project_with(doc: Document) -> Project:
    return make_project(documents=[doc])


@pytest.mark.unit
async def test__get_document__variant_doc__resolves_paths_name_and_null_engine(pres_definition) -> None:
    # copy-only вариант (pptx): пути из варианта, engine — None
    project = _project_with(make_document("pres", chosen_variant="pptx"))
    uc = _make_uc(project, documents=(pres_definition,))

    out = await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="pres"))

    assert out.document.id == "pres"
    assert out.name == {"ru": "pres"}
    assert out.code == {"ru": "PRES"}
    assert out.source_file == "pres/pptx/presentation.pptx"
    assert out.output_file == "pres/pptx/presentation.pptx"
    assert out.engine is None


@pytest.mark.unit
async def test__get_document__variant_doc__beamer_engine_from_variant(pres_definition) -> None:
    project = _project_with(make_document("pres", chosen_variant="beamer"))
    uc = _make_uc(project, documents=(pres_definition,))

    out = await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="pres"))

    assert out.source_file == "pres/beamer/pres.tex"
    assert out.output_file == "pres/beamer/pres.pdf"
    assert out.engine == "xelatex"


@pytest.mark.unit
async def test__get_document__plain_doc__engine_from_project_lock() -> None:
    project = _project_with(make_document("vkr"))
    uc = _make_uc(project, documents=(make_document_definition("vkr"),))

    out = await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="vkr"))

    assert out.source_file == "vkr/main.tex"
    assert out.output_file == "vkr/main.pdf"
    # Без вариантов движок берётся из lock проекта
    assert out.engine == str(project.lock.engine)


@pytest.mark.unit
async def test__get_document__pptx_with_converted_pdf__exposes_preview_file(tmp_path, pres_definition) -> None:
    # Сборка pptx-варианта кладёт рядом PDF-предпросмотр (Gotenberg) —
    # detail отдаёт его как preview_file.
    (tmp_path / "pres" / "pptx").mkdir(parents=True)
    (tmp_path / "pres" / "pptx" / "presentation.pdf").write_bytes(b"%PDF-1.7")
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    uc = _make_uc(project, documents=(pres_definition,))

    out = await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="pres"))

    assert out.preview_file == "pres/pptx/presentation.pdf"


@pytest.mark.unit
async def test__get_document__pptx_without_converted_pdf__no_preview_file(tmp_path, pres_definition) -> None:
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    uc = _make_uc(project, documents=(pres_definition,))

    out = await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="pres"))

    assert out.preview_file is None


@pytest.mark.unit
async def test__get_document__pdf_artifact__never_reports_preview(tmp_path, pres_definition) -> None:
    # PDF-артефакт (beamer) сам себе предпросмотр — preview_file не заполняется.
    (tmp_path / "pres" / "beamer").mkdir(parents=True)
    (tmp_path / "pres" / "beamer" / "pres.pdf").write_bytes(b"%PDF-1.7")
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="beamer")])
    uc = _make_uc(project, documents=(pres_definition,))

    out = await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="pres"))

    assert out.preview_file is None


@pytest.mark.unit
async def test__get_document__missing_document__raises() -> None:
    project = _project_with(make_document("vkr"))
    uc = _make_uc(project, documents=(make_document_definition("vkr"),))

    with pytest.raises(NotFoundError, match="не найден"):
        await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="ghost"))


@pytest.mark.unit
async def test__get_document__custom_file_pdf__signing_available_no_preview_flag(tmp_path) -> None:
    custom = make_custom_file_override(original_filename="my.pdf", stored_path="vkr/_custom/my.pdf", ext=".pdf")
    project = make_project(folder=tmp_path, documents=[make_document("vkr", custom_file=custom)])
    uc = _make_uc(project, documents=(make_document_definition("vkr"),))

    out = await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="vkr"))

    assert out.preview_file == "vkr/_custom/my.pdf"
    assert out.signing_available is True


@pytest.mark.unit
async def test__get_document__custom_file_docx_with_sibling_pdf__preview_and_signable(tmp_path) -> None:
    (tmp_path / "vkr" / "_custom").mkdir(parents=True)
    (tmp_path / "vkr" / "_custom" / "ТЗ.pdf").write_bytes(b"%PDF-1.7")
    custom = make_custom_file_override(original_filename="ТЗ.docx", stored_path="vkr/_custom/ТЗ.docx", ext=".docx")
    project = make_project(folder=tmp_path, documents=[make_document("vkr", custom_file=custom)])
    uc = _make_uc(project, documents=(make_document_definition("vkr"),))

    out = await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="vkr"))

    assert out.preview_file == "vkr/_custom/ТЗ.pdf"
    assert out.custom_preview_available is True
    assert out.signing_available is True


@pytest.mark.unit
async def test__get_document__custom_file_docx_without_preview__unsignable(tmp_path) -> None:
    custom = make_custom_file_override(original_filename="ТЗ.docx", stored_path="vkr/_custom/ТЗ.docx", ext=".docx")
    project = make_project(folder=tmp_path, documents=[make_document("vkr", custom_file=custom)])
    uc = _make_uc(project, documents=(make_document_definition("vkr"),))

    out = await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="vkr"))

    assert out.preview_file is None
    assert out.custom_preview_available is False
    assert out.signing_available is False


@pytest.mark.unit
async def test__get_document__no_custom_file__signing_always_available() -> None:
    project = _project_with(make_document("vkr"))
    uc = _make_uc(project, documents=(make_document_definition("vkr"),))

    out = await uc.execute(GetDocumentInput(project_id=uuid4(), doc_id="vkr"))

    assert out.signing_available is True
