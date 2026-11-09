"""create_project: схема и проверка зависят от режима (на общем сервере папку выбирает сервер), авторы и
руководители разбираются так же, как их собирает мастер создания в вебе (одиночный и командный проект)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat, PersonRole, ProjectStaffing
from hse_doc_studio.core.team import normalize_team_authors
from hse_doc_studio.core.value_objects import Author, Person
from hse_doc_studio.use_cases.chat.tools.create_project import CreateProjectTool
from hse_doc_studio.use_cases.projects.create_project import CreateProjectInput

_ARGS = {"name": "ВКР", "pack_id": "hse-cs-se", "template_id": "vkr", "version": "2026.1"}


class _CreateUC:
    """Сценарий создания: запоминает вход и, как настоящий, на сервере не принимает folder."""

    def __init__(self, *, server: bool) -> None:
        self.server_allocates_folder = server
        self.inputs: list[CreateProjectInput] = []

    async def execute(self, inp: CreateProjectInput) -> Any:
        if self.server_allocates_folder and inp.folder is not None:
            raise ValueError("folder не принимается")
        self.inputs.append(inp)
        folder = inp.folder or Path("/srv/projects") / "p"
        project = SimpleNamespace(
            name=inp.name, id=uuid4(), folder=folder, staffing=inp.staffing, authors=normalize_team_authors(inp.authors)
        )
        return SimpleNamespace(project=project)


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=UUID(int=0), model="m", edit_format=EditFormat.search_replace)


def _tool(*, server: bool) -> tuple[CreateProjectTool, _CreateUC]:
    uc = _CreateUC(server=server)
    return CreateProjectTool(uc), uc  # type: ignore[arg-type]


@pytest.mark.parametrize("server", [True, False])
def test__spec__no_ask_user_advice_in_either_mode(server: bool) -> None:
    tool, _ = _tool(server=server)

    assert "ask_user" not in tool.definition().spec.description


def test__spec__server_mode__has_no_folder() -> None:
    tool, _ = _tool(server=True)

    params = tool.definition().spec.parameters

    assert "folder" not in params["properties"]
    assert params["required"] == ["name", "pack_id", "template_id", "version"]


def test__spec__local_mode__folder_is_required() -> None:
    tool, _ = _tool(server=False)

    params = tool.definition().spec.parameters

    assert "folder" in params["properties"]
    assert "folder" in params["required"]


@pytest.mark.parametrize("folder", [None, "", "   ", "/home/anna/vkr"])
async def test__handle__server_mode__creates_without_folder(folder: str | None) -> None:
    tool, uc = _tool(server=True)
    args: dict[str, object] = dict(_ARGS)
    if folder is not None:
        args["folder"] = folder

    result = await tool.handle(_ctx(), args)

    assert result.is_error is False, result.text
    assert uc.inputs[0].folder is None


async def test__handle__server_mode__missing_name__error_does_not_ask_for_folder() -> None:
    tool, uc = _tool(server=True)

    result = await tool.handle(_ctx(), {**_ARGS, "name": " "})

    assert result.is_error is True
    assert "folder" not in result.text
    assert uc.inputs == []


@pytest.mark.parametrize("folder", [None, "", "   "])
async def test__handle__local_mode__blank_folder__is_rejected(folder: str | None) -> None:
    tool, uc = _tool(server=False)
    args: dict[str, object] = dict(_ARGS)
    if folder is not None:
        args["folder"] = folder

    result = await tool.handle(_ctx(), args)

    assert result.is_error is True
    assert "folder" in result.text
    assert uc.inputs == []


async def test__handle__local_mode__passes_the_folder(tmp_path: Path) -> None:
    tool, uc = _tool(server=False)

    result = await tool.handle(_ctx(), {**_ARGS, "folder": str(tmp_path / "vkr")})

    assert result.is_error is False, result.text
    assert uc.inputs[0].folder == tmp_path / "vkr"


def _team_author(name: str, topic: str, **extra: object) -> dict[str, object]:
    return {"name": name, "topic": topic, **extra}


_TEAM = [_team_author("Смирнова Анна", "Сервер"), _team_author("Петров Борис", "Клиент", group="БПИ222")]


@pytest.mark.parametrize("server", [True, False])
def test__spec__team_fields_in_both_modes(server: bool) -> None:
    tool, _ = _tool(server=server)

    spec = tool.definition().spec
    props = spec.parameters["properties"]

    assert {"authors", "author_name", "shared_enabled", "supervisor", "co_supervisor", "academic_supervisor"} <= set(
        props
    )
    assert set(props["authors"]["items"]["properties"]) == {"name", "group", "email", "topic", "slug", "managed"}
    assert "authors" not in spec.parameters["required"]
    assert "team" in spec.description


async def test__handle__author_name_only__solo_project_as_before() -> None:
    tool, uc = _tool(server=True)

    result = await tool.handle(_ctx(), {**_ARGS, "author_name": "Иванов Иван"})

    assert result.is_error is False, result.text
    (inp,) = uc.inputs
    assert inp.staffing is ProjectStaffing.solo
    assert inp.authors == [Author(name="Иванов Иван")]
    assert (inp.supervisor, inp.co_supervisor, inp.meta, inp.shared_enabled) == (None, None, {}, True)
    assert "комплекты" not in result.text


async def test__handle__no_authors__solo_project_without_authors() -> None:
    tool, uc = _tool(server=True)

    result = await tool.handle(_ctx(), dict(_ARGS))

    assert result.is_error is False, result.text
    assert uc.inputs[0].authors == []
    assert uc.inputs[0].staffing is ProjectStaffing.solo


async def test__handle__several_authors__team_project_like_the_wizard() -> None:
    tool, uc = _tool(server=True)
    authors = [*_TEAM, _team_author("Вера Козлова", "", managed=False, slug="vera", email="vera@edu.hse.ru")]

    result = await tool.handle(_ctx(), {**_ARGS, "authors": authors, "shared_enabled": False})

    assert result.is_error is False, result.text
    (inp,) = uc.inputs
    assert inp.staffing is ProjectStaffing.team
    assert inp.shared_enabled is False
    assert inp.authors == [
        Author(name="Смирнова Анна", topic="Сервер"),
        Author(name="Петров Борис", group="БПИ222", topic="Клиент"),
        Author(name="Вера Козлова", email="vera@edu.hse.ru", slug="vera", managed=False),
    ]
    # Как мастер: группа первого автора, у кого она есть, идёт в meta.group.
    assert inp.meta == {"group": "БПИ222"}
    assert "smirnova (Смирнова Анна), petrov (Петров Борис)" in result.text


async def test__handle__supervisors__parsed_like_set_project_people() -> None:
    tool, uc = _tool(server=True)

    result = await tool.handle(
        _ctx(),
        {
            **_ARGS,
            "authors": [{"name": "Иванов Иван"}],
            "supervisor": {"name": "Петров П. П.", "title": "доцент", "degree": "канд. техн. наук"},
            "co_supervisor": {"name": "Сидоров С. С.", "role": "company"},
            "academic_supervisor": {"name": ""},
        },
    )

    assert result.is_error is False, result.text
    (inp,) = uc.inputs
    assert inp.staffing is ProjectStaffing.solo
    assert inp.supervisor == Person(
        name="Петров П. П.", role=PersonRole.university, title="доцент", degree="канд. техн. наук"
    )
    assert inp.co_supervisor == Person(name="Сидоров С. С.", role=PersonRole.company)
    assert inp.academic_supervisor is None


async def test__handle__solo__team_only_fields_are_ignored() -> None:
    tool, uc = _tool(server=True)

    result = await tool.handle(
        _ctx(), {**_ARGS, "authors": [{"name": "Иванов", "managed": False}], "shared_enabled": False}
    )

    assert result.is_error is False, result.text
    assert uc.inputs[0].authors == [Author(name="Иванов")]
    assert uc.inputs[0].shared_enabled is True


async def test__handle__explicit_team_with_one_author__left_to_the_use_case() -> None:
    """Минимум двух авторов и поддержку шаблоном проверяет CreateProjectUC, как для веба."""
    tool, uc = _tool(server=True)

    result = await tool.handle(_ctx(), {**_ARGS, "staffing": "team", "authors": [_TEAM[0]]})

    assert result.is_error is False, result.text
    assert uc.inputs[0].staffing is ProjectStaffing.team


@pytest.mark.parametrize(
    ("extra", "needle"),
    [
        ({"authors": _TEAM, "author_name": "Иванов"}, "author_name"),
        ({"authors": _TEAM, "staffing": "solo"}, "staffing team"),
        ({"authors": [_TEAM[0], _team_author("Петров", "")]}, "topic"),
        ({"authors": [{**a, "managed": False} for a in _TEAM]}, "managed"),
        ({"authors": [{**_TEAM[0], "slug": "x"}, {**_TEAM[1], "slug": "x"}]}, "slug"),
        ({"authors": [{**_TEAM[0], "slug": "Anna!"}, _TEAM[1]]}, "slug"),
        ({"authors": [{**_TEAM[0], "slug": "shared"}, _TEAM[1]]}, "slug"),
        ({"authors": [{**_TEAM[0], "managed": "yes"}, _TEAM[1]]}, "managed"),
        ({"authors": _TEAM, "shared_enabled": "no"}, "shared_enabled"),
        ({"authors": [{"group": "Г1"}]}, "name"),
        ({"authors": []}, "authors"),
        ({"authors": [{"name": "Иванов", "email": "нет"}]}, "email"),
        ({"supervisor": {"title": "доцент"}}, "supervisor"),
        ({"co_supervisor": {"name": "Сидоров", "role": "boss"}}, "co_supervisor.role"),
    ],
)
async def test__handle__bad_people__error_and_nothing_created(extra: dict[str, object], needle: str) -> None:
    tool, uc = _tool(server=True)

    result = await tool.handle(_ctx(), {**_ARGS, **extra})

    assert result.is_error is True
    assert needle in result.text
    assert uc.inputs == []
