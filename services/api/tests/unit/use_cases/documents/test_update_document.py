from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import DocumentStatus
from hse_doc_studio.infra.project_init.template_renderer import TemplateRenderer
from hse_doc_studio.use_cases.documents.update_document import (
    InvalidVariantError,
    UpdateDocumentInput,
    UpdateDocumentUC,
)

from tests.factories import make_document, make_document_definition, make_project, make_template_version


def _make_uc(project: Project, documents: tuple = (), template_repo: MagicMock | None = None) -> UpdateDocumentUC:
    if template_repo is None:
        template_repo = MagicMock()
    template_repo.get_version.return_value = make_template_version(documents=documents)
    uc = UpdateDocumentUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        template_repo=template_repo,
        template_renderer=TemplateRenderer(),
    )
    uc._get_uc = AsyncMock()
    uc._get_uc.execute.return_value = SimpleNamespace(project=project)
    return uc


def _switch_env(tmp_path: Path) -> tuple[Project, MagicMock]:
    """Пак с двумя вариантами pres; проект создан ДО материализации всех
    вариантов (лежит только pptx, причём правленный студентом)."""
    files_dir = tmp_path / "packs" / "hse-cs-se" / "templates" / "vkr" / "versions" / "1.0" / "files"
    (files_dir / "pres" / "pptx").mkdir(parents=True)
    (files_dir / "pres" / "pptx" / "presentation.pptx").write_bytes(b"pack pptx")
    (files_dir / "pres" / "beamer").mkdir()
    (files_dir / "pres" / "beamer" / "pres.tex").write_text("pack beamer {{ project.name }}", encoding="utf-8")
    (files_dir / "common").mkdir()
    (files_dir / "common" / "preamble.tex").write_text("pack preamble", encoding="utf-8")
    (files_dir / ".latexmkrc").write_text("pack rc", encoding="utf-8")

    project = make_project(
        folder=tmp_path / "project",
        documents=[make_document("pres", status=DocumentStatus.ok, chosen_variant="pptx")],
    )
    (project.folder / "pres" / "pptx").mkdir(parents=True)
    (project.folder / "pres" / "pptx" / "presentation.pptx").write_bytes(b"edited by student")

    template_repo = MagicMock()
    template_repo._packs_dir = str(tmp_path / "packs")
    template_repo.list_packs.return_value = [SimpleNamespace(id="hse-cs-se", templates=[SimpleNamespace(id="vkr")])]
    return project, template_repo


@pytest.mark.unit
async def test__update_document__unknown_variant_id__raises_invalid_variant(pres_definition) -> None:
    project = make_project(documents=[make_document("pres", chosen_variant="pptx")])
    uc = _make_uc(project, documents=(pres_definition,))

    with pytest.raises(InvalidVariantError, match="keynote"):
        await uc.execute(UpdateDocumentInput(project_id=uuid4(), doc_id="pres", chosen_variant="keynote"))
    # Ошибка — до мутации: выбор и статус не тронуты.
    assert project.documents[0].chosen_variant == "pptx"


@pytest.mark.unit
async def test__update_document__variant_on_doc_without_variants__raises_invalid_variant() -> None:
    project = make_project(documents=[make_document("vkr")])
    uc = _make_uc(project, documents=(make_document_definition("vkr"),))

    with pytest.raises(InvalidVariantError, match="нет вариантов"):
        await uc.execute(UpdateDocumentInput(project_id=uuid4(), doc_id="vkr", chosen_variant="pptx"))


@pytest.mark.unit
async def test__update_document__switch__resets_status_and_materialises_missing_files(
    tmp_path: Path, pres_definition
) -> None:
    project, template_repo = _switch_env(tmp_path)
    uc = _make_uc(project, documents=(pres_definition,), template_repo=template_repo)

    out = await uc.execute(UpdateDocumentInput(project_id=uuid4(), doc_id="pres", chosen_variant="beamer"))

    assert out.document.chosen_variant == "beamer"
    # Прошлые сборка/проверки принадлежали другому варианту — статус сброшен.
    assert out.document.status == DocumentStatus.draft
    # Файлы beamer-варианта доложены из пака (проект создан до «всех вариантов»)…
    beamer_tex = project.folder / "pres" / "beamer" / "pres.tex"
    assert beamer_tex.read_text(encoding="utf-8") == "pack beamer Test Project"
    # …правленный файл текущего варианта НЕ перезаписан (lossless)…
    assert (project.folder / "pres" / "pptx" / "presentation.pptx").read_bytes() == b"edited by student"
    # …а чужие каталоги/корневые файлы пака в проект не тащатся.
    assert not (project.folder / "common").exists()
    assert not (project.folder / ".latexmkrc").exists()


@pytest.mark.unit
async def test__update_document__null_variant__resets_to_first(tmp_path: Path, pres_definition) -> None:
    project, template_repo = _switch_env(tmp_path)
    project.documents[0].chosen_variant = "beamer"
    uc = _make_uc(project, documents=(pres_definition,), template_repo=template_repo)

    out = await uc.execute(UpdateDocumentInput(project_id=uuid4(), doc_id="pres", chosen_variant=None))

    # null — сброс к дефолту (первый вариант определения).
    assert out.document.chosen_variant == "pptx"
    assert out.document.status == DocumentStatus.draft


@pytest.mark.unit
async def test__update_document__same_variant__noop_keeps_status(pres_definition) -> None:
    project = make_project(documents=[make_document("pres", status=DocumentStatus.ok, chosen_variant="pptx")])
    uc = _make_uc(project, documents=(pres_definition,))

    out = await uc.execute(UpdateDocumentInput(project_id=uuid4(), doc_id="pres", chosen_variant="pptx"))

    assert out.document.chosen_variant == "pptx"
    assert out.document.status == DocumentStatus.ok


@pytest.mark.unit
async def test__update_document__materialisation_failure_does_not_fail_patch(pres_definition) -> None:
    # Пака на диске нет (кривой _packs_dir) — смена варианта всё равно
    # применяется: материализация best-effort.
    project = make_project(documents=[make_document("pres", status=DocumentStatus.ok, chosen_variant="pptx")])
    uc = _make_uc(project, documents=(pres_definition,))

    out = await uc.execute(UpdateDocumentInput(project_id=uuid4(), doc_id="pres", chosen_variant="beamer"))

    assert out.document.chosen_variant == "beamer"
    assert out.document.status == DocumentStatus.draft
