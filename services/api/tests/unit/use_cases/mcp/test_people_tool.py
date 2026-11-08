"""set_project_people: разбор аргументов, слияние с текущими людьми проекта и запись в аудит."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat, PersonRole, ProjectStaffing
from hse_doc_studio.core.mcp.protocols import IMcpChangeAudit
from hse_doc_studio.core.value_objects import Author, Person
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.mcp.tools.people import (
    PEOPLE_AUDIT_ACTION,
    SetProjectPeopleTool,
    merge_authors,
    merge_person,
    update_author,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.projects.update_project import UpdateProjectInput, UpdateProjectUC

_SUPERVISOR = Person(name="Петров П. П.", role=PersonRole.university, title="доцент", degree="канд. техн. наук")


def test__merge_person__keeps_fields_that_were_not_passed() -> None:
    merged = merge_person(_SUPERVISOR, {"degree": "д-р техн. наук"}, "supervisor")

    assert merged == replace(_SUPERVISOR, degree="д-р техн. наук")


def test__merge_person__empty_string_clears_title() -> None:
    merged = merge_person(_SUPERVISOR, {"title": " "}, "supervisor")

    assert merged.title is None
    assert merged.name == _SUPERVISOR.name


def test__merge_person__new_person__needs_a_name_and_defaults_to_university() -> None:
    with pytest.raises(ArgumentError, match="name"):
        merge_person(None, {"title": "доцент"}, "co_supervisor")

    created = merge_person(None, {"name": "Сидоров С. С."}, "co_supervisor")
    assert created == Person(name="Сидоров С. С.", role=PersonRole.university)


def test__merge_person__empty_name__removes_the_person() -> None:
    assert merge_person(_SUPERVISOR, {"name": ""}, "supervisor") is None


@pytest.mark.parametrize("raw", [{"role": "boss"}, {"name": 5}, "Петров"])
def test__merge_person__bad_values__rejected(raw: object) -> None:
    with pytest.raises(ArgumentError):
        merge_person(_SUPERVISOR, raw, "supervisor")


def test__merge_authors__by_position__keeps_email_and_team_fields() -> None:
    current = [Author(name="Иванов И.", group="БПИ221", email="i@hse.ru", slug="ivanov", topic="Сервер")]

    (author,) = merge_authors(current, [{"name": "Иванов Иван Иванович"}])

    assert author == replace(current[0], name="Иванов Иван Иванович")


def test__merge_authors__by_slug__survives_reordering_and_new_author_gets_no_foreign_slug() -> None:
    anna = Author(name="Анна", group="Г1", slug="anna", topic="A")
    boris = Author(name="Борис", group="Г2", slug="boris", topic="B")

    merged = merge_authors(
        [anna, boris],
        [
            {"name": "Борис Б.", "slug": "boris"},
            {"name": "Анна А.", "slug": "anna", "group": "Г3"},
            {"name": "Вера", "slug": "zzz"},
        ],
    )

    assert merged == [
        replace(boris, name="Борис Б."),
        replace(anna, name="Анна А.", group="Г3"),
        Author(name="Вера"),
    ]


def test__merge_authors__email__set_kept_and_cleared() -> None:
    current = [Author(name="Иванов", email="i@hse.ru"), Author(name="Петров", email="p@hse.ru")]

    merged = merge_authors(current, [{"name": "Иванов", "email": "ivanov@edu.hse.ru"}, {"name": "Петров", "email": ""}])

    assert [a.email for a in merged] == ["ivanov@edu.hse.ru", None]
    assert merge_authors(current, [{"name": "Иванов"}])[0].email == "i@hse.ru"


@pytest.mark.parametrize(
    "raw",
    [[], "Иванов", [{"group": "Г1"}], [{"name": " "}], [{"name": "x"}] * 21, [{"name": "x", "email": "нет"}]],
)
def test__merge_authors__bad_list__rejected(raw: object) -> None:
    with pytest.raises(ArgumentError):
        merge_authors([], raw)


def _project(staffing: ProjectStaffing, *authors: Author) -> Any:
    return SimpleNamespace(staffing=staffing, authors=list(authors))


def test__update_author__solo__changes_the_first_author_and_keeps_the_rest() -> None:
    first = Author(name="Иванов И.", group="БПИ221", email="old@hse.ru")
    second = Author(name="Петров П.")

    updated = update_author(_project(ProjectStaffing.solo, first, second), {"group": "МПИ251", "email": "i@edu.hse.ru"})

    assert updated == [replace(first, group="МПИ251", email="i@edu.hse.ru"), second]


def test__update_author__solo_without_authors__creates_one() -> None:
    assert update_author(_project(ProjectStaffing.solo), {"name": "Иванов", "group": "МПИ251"}) == [
        Author(name="Иванов", group="МПИ251")
    ]


def test__update_author__team__picks_by_slug_and_empty_value_clears() -> None:
    anna = Author(name="Анна", group="Г1", email="a@hse.ru", slug="anna", topic="A")
    boris = Author(name="Борис", group="Г2", slug="boris")

    updated = update_author(_project(ProjectStaffing.team, anna, boris), {"slug": "anna", "group": ""})

    assert updated == [replace(anna, group=None), boris]


@pytest.mark.parametrize(
    "raw",
    [
        {"group": "Г3"},  # командный проект без slug
        {"slug": "zzz", "group": "Г3"},  # нет такого автора
        {"slug": "anna"},  # нечего менять
        {"slug": "anna", "name": ""},  # ФИО не очищается
        {"slug": "anna", "email": "anna"},  # не адрес
        "anna",
    ],
)
def test__update_author__team__bad_arguments__rejected(raw: object) -> None:
    with pytest.raises(ArgumentError):
        update_author(_project(ProjectStaffing.team, Author(name="Анна", slug="anna")), raw)


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, str | None, Mapping[str, object]]] = []

    async def record(self, action: str, *, target: str | None, details: Mapping[str, object]) -> None:
        self.events.append((action, target, details))


class _Store:
    """Проект в памяти и тот же порядок, что у настоящего UpdateProjectUC: поле меняется, если оно передано."""

    def __init__(self, project: Any) -> None:
        self.project = project
        self.inputs: list[UpdateProjectInput] = []

    async def execute(self, inp: Any) -> Any:
        if isinstance(inp, UpdateProjectInput):
            self.inputs.append(inp)
            if inp.authors is not None:
                self.project.authors = inp.authors
            for field in ("supervisor", "co_supervisor", "academic_supervisor"):
                value = getattr(inp, field)
                if value is None or isinstance(value, Person):
                    setattr(self.project, field, value)
        return SimpleNamespace(project=self.project)


class _Deps:
    def __init__(self, store: _Store, audit: _Audit) -> None:
        self._by_type: dict[object, object] = {GetProjectUC: store, UpdateProjectUC: store, IMcpChangeAudit: audit}

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        return self._by_type[dependency_type]


def _setup() -> tuple[SetProjectPeopleTool, _Store, _Audit, UUID]:
    project = SimpleNamespace(
        staffing=ProjectStaffing.solo,
        authors=[Author(name="Иванов И.", group="БПИ221")],
        supervisor=_SUPERVISOR,
        co_supervisor=None,
        academic_supervisor=None,
    )
    store, audit = _Store(project), _Audit()
    return SetProjectPeopleTool(_Deps(store, audit)), store, audit, uuid4()  # type: ignore[arg-type]


def _ctx(project_id: UUID) -> AgentToolContext:
    return AgentToolContext(project_id=project_id, model="mcp-client", edit_format=EditFormat.search_replace)


async def test__handle__sets_people_through_update_project_and_audits_the_change() -> None:
    tool, store, audit, project_id = _setup()

    result = await tool.handle(
        _ctx(project_id),
        {
            "supervisor": {"title": "профессор"},
            "co_supervisor": {"name": "Сидоров С. С.", "role": "company", "title": "ведущий инженер"},
            "authors": [{"name": "Иванов Иван", "group": "БПИ222"}],
        },
    )

    assert result.is_error is False, result.text
    assert store.project.supervisor == replace(_SUPERVISOR, title="профессор")
    assert store.project.co_supervisor == Person(name="Сидоров С. С.", role=PersonRole.company, title="ведущий инженер")
    assert store.project.authors == [Author(name="Иванов Иван", group="БПИ222")]
    ((action, target, details),) = audit.events
    assert (action, target) == (PEOPLE_AUDIT_ACTION, str(project_id))
    assert details["fields"] == ["supervisor", "co_supervisor", "authors"]
    assert details["before"]["co_supervisor"] is None  # type: ignore[index]
    assert details["after"]["supervisor"]["title"] == "профессор"  # type: ignore[index]


async def test__handle__clear__removes_the_supervisor_only() -> None:
    tool, store, audit, project_id = _setup()

    result = await tool.handle(_ctx(project_id), {"clear": ["supervisor"]})

    assert result.is_error is False, result.text
    assert store.project.supervisor is None
    assert store.inputs[0].authors is None
    assert audit.events[0][2]["fields"] == ["supervisor"]


async def test__handle__author_and_empty_supervisor_name__update_author_and_remove_supervisor() -> None:
    tool, store, audit, project_id = _setup()

    result = await tool.handle(
        _ctx(project_id), {"supervisor": {"name": ""}, "author": {"group": "МПИ251", "email": "i@edu.hse.ru"}}
    )

    assert result.is_error is False, result.text
    assert store.project.supervisor is None
    assert store.project.authors == [Author(name="Иванов И.", group="МПИ251", email="i@edu.hse.ru")]
    assert audit.events[0][2]["fields"] == ["supervisor", "authors"]
    assert audit.events[0][2]["after"]["authors"][0]["email"] == "i@edu.hse.ru"  # type: ignore[index]


async def test__handle__same_values__no_audit_event() -> None:
    tool, _, audit, project_id = _setup()

    result = await tool.handle(_ctx(project_id), {"supervisor": {"name": _SUPERVISOR.name}})

    assert result.is_error is False
    assert audit.events == []


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"clear": ["authors"]},
        {"clear": "supervisor"},
        {"clear": ["supervisor"], "supervisor": {"name": "X"}},
        {"author": {"group": "Г"}, "authors": [{"name": "X"}]},
    ],
)
async def test__handle__nothing_or_contradictory__argument_error_and_no_write(args: dict[str, object]) -> None:
    tool, store, audit, project_id = _setup()

    with pytest.raises(ArgumentError):
        await tool.handle(_ctx(project_id), args)

    assert store.inputs == []
    assert audit.events == []
