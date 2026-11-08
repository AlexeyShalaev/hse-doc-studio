"""set_document_variant: смена через UpdateDocumentUC, перечень вариантов шаблона, отказ и аудит."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.catalog import DocumentDefinition, DocumentVariant
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import DocumentStatus, EditFormat
from hse_doc_studio.core.mcp.protocols import IMcpChangeAudit
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.infra.project_init.template_renderer import TemplateRenderer
from hse_doc_studio.use_cases.documents.update_document import UpdateDocumentUC
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.mcp.tools.documents import VARIANT_AUDIT_ACTION, SetDocumentVariantTool
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC

from tests.factories import make_document, make_document_definition, make_project, make_template_version


def _variant(variant_id: str, source: str, *langs: str) -> DocumentVariant:
    return DocumentVariant(
        id=variant_id,
        label={"ru": variant_id.capitalize()},
        source_file=source,
        output_file=source,
        output_name={"ru": source},
        engine=None,
        supported_langs=langs,
    )


@pytest.fixture
def pres_definition() -> DocumentDefinition:
    variants = (
        _variant("pptx", "pres/pptx/presentation.pptx"),
        _variant("beamer", "pres/beamer/pres.tex"),
        _variant("reveal", "pres/reveal/index.html", "en"),
    )
    return make_document_definition("pres", required=False, variants=variants)


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None, Mapping[str, object]]] = []

    async def record(self, action: str, *, target: str | None, details: Mapping[str, object]) -> None:
        self.events.append((action, target, details))


class _Deps:
    def __init__(self, by_type: dict[object, object]) -> None:
        self._by_type = by_type

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        return self._by_type[dependency_type]


def _setup(tmp_path: Path, definition: DocumentDefinition) -> tuple[SetDocumentVariantTool, Project, _Audit]:
    project = make_project(
        folder=tmp_path / "project",
        documents=[make_document("pres", status=DocumentStatus.ok, chosen_variant="pptx"), make_document("vkr")],
    )
    templates = MagicMock()
    templates.get_version.return_value = make_template_version(documents=(definition, make_document_definition("vkr")))
    update = UpdateDocumentUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        template_repo=templates,
        template_renderer=TemplateRenderer(),
    )
    found = SimpleNamespace(project=project)
    update._get_uc = AsyncMock()  # noqa: SLF001 — проект в памяти вместо репозитория
    update._get_uc.execute.return_value = found  # noqa: SLF001
    get_project = AsyncMock()
    get_project.execute.return_value = found
    audit = _Audit()
    deps = _Deps(
        {GetProjectUC: get_project, UpdateDocumentUC: update, ITemplateRepository: templates, IMcpChangeAudit: audit}
    )
    return SetDocumentVariantTool(deps), project, audit  # type: ignore[arg-type]


def _ctx(project_id: UUID) -> AgentToolContext:
    return AgentToolContext(project_id=project_id, model="mcp-client", edit_format=EditFormat.search_replace)


async def test__handle__switches_through_update_document_and_audits(
    tmp_path: Path, pres_definition: DocumentDefinition
) -> None:
    tool, project, audit = _setup(tmp_path, pres_definition)
    project_id = uuid4()

    result = await tool.handle(_ctx(project_id), {"doc_id": "pres", "variant": "beamer"})

    assert result.is_error is False, result.text
    view = json.loads(result.text)
    assert (view["variant"], view["changed"], view["status"]) == ("beamer", True, "draft")
    assert project.documents[0].chosen_variant == "beamer"
    ((action, target, details),) = audit.events
    assert (action, target) == (VARIANT_AUDIT_ACTION, str(project_id))
    assert (details["doc_id"], details["before"], details["after"]) == ("pres", "pptx", "beamer")


async def test__handle__no_variant__lists_selectable_variants_without_change(
    tmp_path: Path, pres_definition: DocumentDefinition
) -> None:
    tool, project, audit = _setup(tmp_path, pres_definition)

    result = await tool.handle(_ctx(uuid4()), {"doc_id": "pres"})

    view = json.loads(result.text)
    # reveal только для англоязычного проекта: в русском его нет, как в настройках проекта.
    assert [(v["id"], v["current"]) for v in view["variants"]] == [("pptx", True), ("beamer", False)]
    assert view["changed"] is False
    assert project.documents[0].status is DocumentStatus.ok
    assert audit.events == []


async def test__handle__same_variant__no_audit(tmp_path: Path, pres_definition: DocumentDefinition) -> None:
    tool, _, audit = _setup(tmp_path, pres_definition)

    result = await tool.handle(_ctx(uuid4()), {"doc_id": "pres", "variant": "pptx"})

    assert json.loads(result.text)["changed"] is False
    assert audit.events == []


@pytest.mark.parametrize("variant", ["keynote", "reveal"])
async def test__handle__not_allowed_variant__lists_allowed_and_changes_nothing(
    tmp_path: Path, pres_definition: DocumentDefinition, variant: str
) -> None:
    tool, project, audit = _setup(tmp_path, pres_definition)

    with pytest.raises(ArgumentError, match="pptx, beamer"):
        await tool.handle(_ctx(uuid4()), {"doc_id": "pres", "variant": variant})

    assert project.documents[0].chosen_variant == "pptx"
    assert audit.events == []


@pytest.mark.parametrize(("doc_id", "message"), [("thesis", "pres, vkr"), ("vkr", "нет вариантов")])
async def test__handle__unknown_document_or_no_variants__argument_error(
    tmp_path: Path, pres_definition: DocumentDefinition, doc_id: str, message: str
) -> None:
    tool, _, audit = _setup(tmp_path, pres_definition)

    with pytest.raises(ArgumentError, match=message):
        await tool.handle(_ctx(uuid4()), {"doc_id": doc_id, "variant": "pptx"})

    assert audit.events == []
