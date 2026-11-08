"""create_project: схема и проверка зависят от режима (на общем сервере папку выбирает сервер)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
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
        return SimpleNamespace(project=SimpleNamespace(name=inp.name, id=uuid4(), folder=folder))


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
