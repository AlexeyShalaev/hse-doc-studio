"""list_project_fields по настоящим пакам и удаление ключей метаданных в set_project_meta."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import EditFormat, PersonRole, ProjectKind, ProjectStaffing
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.value_objects import Author, Person
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.chat.tools.set_project_meta import SetProjectMetaTool
from hse_doc_studio.use_cases.mcp.tools.fields import ListProjectFieldsTool
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.projects.project_fields import list_project_fields
from hse_doc_studio.use_cases.projects.update_project import UpdateProjectInput

from tests.factories import make_project

_PACKS = Path(__file__).resolve().parents[6] / "packs"


@pytest.fixture(scope="module")
def templates() -> YamlTemplateRepository:
    return YamlTemplateRepository(_PACKS)


def _project(pack: str, template: str, version: str, **changes: Any) -> Project:
    project = make_project()
    project.lock = dataclasses.replace(project.lock, pack_id=pack, template_id=template, version=version)
    for key, value in changes.items():
        setattr(project, key, value)
    return project


def _fields(templates: YamlTemplateRepository, project: Project) -> dict[str, Any]:
    lock = project.lock
    version = templates.get_version(lock.pack_id, lock.template_id, lock.version)
    version_dir = templates.version_dir(lock.pack_id, lock.template_id, lock.version)
    assert version is not None
    assert version_dir is not None
    return {f.key: f for f in list_project_fields(project, version, version_dir / "files")}


def test__list_project_fields__msc_coursework__values_and_documents(templates: YamlTemplateRepository) -> None:
    supervisor = Person(name="С. А. Шершаков", role=PersonRole.university)
    project = _project(
        "hse-cs-sse", "coursework", "2026.1.2", kind=ProjectKind.project, meta={"udc": "004.4"}, supervisor=supervisor
    )

    fields = _fields(templates, project)

    assert fields["udc"].value == "004.4"
    assert fields["udc"].printed_in == ("report",)
    assert fields["supervisor_department"].printed_in == ("topic_application",)
    assert fields["proposal_stage"].printed_in == ("project_proposal",)
    assert set(fields["name_en"].printed_in) == {"project_proposal", "topic_application", "report", "presentation"}
    assert fields["supervisor"].value == supervisor
    assert fields["supervisor"].is_person
    assert fields["year"].value is None


def test__list_project_fields__hides_fields_of_another_kind_like_the_settings(
    templates: YamlTemplateRepository,
) -> None:
    research = _fields(templates, _project("hse-cs-se", "vkr", "2026.1", kind=ProjectKind.research))
    project = _fields(templates, _project("hse-cs-se", "vkr", "2026.1", kind=ProjectKind.project))

    assert "manuals" not in research
    assert project["manuals"].printed_in == ("technical_specification",)


def test__list_project_fields__team__author_scoped_values_per_slug(templates: YamlTemplateRepository) -> None:
    authors = [
        Author(name="Анна", slug="anna", meta={"name_en": "Server"}),
        Author(name="Борис", slug="boris"),
    ]
    project = _project(
        "hse-cs-se", "vkr", "2026.1", kind=ProjectKind.project, staffing=ProjectStaffing.team, authors=authors
    )

    fields = _fields(templates, project)

    assert fields["name_en"].author_values == {"anna": "Server", "boris": None}
    assert fields["year"].author_values == {}


class _Deps:
    def __init__(self, project: Project, templates: YamlTemplateRepository) -> None:
        self._project = project
        self._templates = templates

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        if dependency_type is GetProjectUC:
            return self
        assert dependency_type is ITemplateRepository
        return self._templates

    async def execute(self, inp: Any) -> Any:
        return type("Out", (), {"project": self._project})()


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=uuid4(), model="mcp-client", edit_format=EditFormat.search_replace)


async def test__tool__answers_labels_required_missing_and_document_names(templates: YamlTemplateRepository) -> None:
    project = _project(
        "hse-cs-sse", "coursework", "2026.1.2", kind=ProjectKind.project, meta={"year": "2027", "group": "МСПИН261"}
    )
    tool = ListProjectFieldsTool(_Deps(project, templates))  # type: ignore[arg-type]

    result = await tool.handle(_ctx(), {})

    assert result.is_error is False, result.text
    data = json.loads(result.text)
    by_key = {f["key"]: f for f in data["fields"]}
    assert data["template"] == "hse-cs-sse/coursework/2026.1.2"
    assert by_key["year"]["value"] == "2027"
    assert (by_key["year"]["required"], by_key["year"]["missing"]) == (True, False)
    assert (by_key["udc"]["required_at"], by_key["udc"]["missing"]) == ("finalize", True)
    assert by_key["udc"]["printed_in"] == [{"id": "report", "name": "Отчёт о курсовом проекте"}]
    assert by_key["proposal_stage"]["options"] == ["Предварительная", "Доработанная"]
    assert by_key["supervisor"]["set_with"] == "set_project_people"
    assert by_key["udc"]["set_with"] == "set_project_meta"
    assert "hint" in by_key["udc"]
    # Группа автора живёт в карточке автора; ключ meta.group шаблон не печатает.
    assert data["unknown_meta"] == {"group": "МСПИН261"}


class _UpdateProject:
    def __init__(self) -> None:
        self.inputs: list[UpdateProjectInput] = []

    async def execute(self, inp: UpdateProjectInput) -> None:
        self.inputs.append(inp)


async def test__set_project_meta__unset__removes_keys_through_update_project() -> None:
    update = _UpdateProject()

    result = await SetProjectMetaTool(update).handle(_ctx(), {"entries": {"year": "2027"}, "unset": ["udc", "udc"]})  # type: ignore[arg-type]

    assert result.is_error is False, result.text
    (inp,) = update.inputs
    assert (inp.meta, inp.meta_unset) == ({"year": "2027"}, ("udc",))


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"entries": {}},
        {"unset": []},
        {"unset": "udc"},
        {"unset": [""]},
        {"entries": {"udc": "1"}, "unset": ["udc"]},
    ],
)
async def test__set_project_meta__nothing_or_contradictory__error_without_write(args: dict[str, object]) -> None:
    update = _UpdateProject()

    result = await SetProjectMetaTool(update).handle(_ctx(), args)  # type: ignore[arg-type]

    assert result.is_error is True
    assert update.inputs == []
