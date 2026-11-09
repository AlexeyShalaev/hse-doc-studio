"""compile_document в MCP: wait=false отвечает сразу, долгая сборка не ошибка, у агента всё как было."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import CompileStatus, EditFormat
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.use_cases.chat._registry import ToolRegistry
from hse_doc_studio.use_cases.chat.tools.compile_document import CompileDocumentTool as AgentCompileDocumentTool
from hse_doc_studio.use_cases.mcp.tools.compile_document import COMPILE_WAIT_S, CompileDocumentTool

from tests.contract.test_compile_contract import make_record
from tests.fakes.compile import InMemoryCompileRepository


class Trigger:
    def __init__(self, compile_id: UUID) -> None:
        self.compile_id = compile_id
        self.calls = 0

    async def execute(self, _input: Any) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(compile_id=self.compile_id)


class Projects:
    def __init__(self, folder: Path) -> None:
        self.folder = folder

    async def execute(self, _input: Any) -> SimpleNamespace:
        return SimpleNamespace(project=SimpleNamespace(folder=self.folder))


class Deps:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def get(self, dependency_type: type[Any], component: str | None = None) -> Any:
        assert dependency_type is ToolRegistry
        return self.registry


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=uuid4(), model="mcp-client", edit_format=EditFormat.search_replace)


async def _agent_tool(tmp_path: Path, status: CompileStatus) -> tuple[AgentCompileDocumentTool, Trigger, UUID]:
    compiles = InMemoryCompileRepository()
    record = make_record(tmp_path, doc_id="tz", status=status)
    await compiles.save(record)
    trigger = Trigger(record.id)
    tool = AgentCompileDocumentTool(trigger, Projects(tmp_path), compiles)  # type: ignore[arg-type]
    return tool, trigger, record.id


def _mcp_tool(agent: AgentCompileDocumentTool) -> CompileDocumentTool:
    return CompileDocumentTool(Deps(ToolRegistry([agent.definition()])))


@pytest.fixture(autouse=True)
def _russian() -> None:
    set_interface_language("ru")


def test__spec__has_wait_flag_defaulting_to_true_and_an_example() -> None:
    props = CompileDocumentTool.spec.parameters["properties"]

    assert props["wait"] == {**props["wait"], "type": "boolean", "default": True}
    assert CompileDocumentTool.spec.parameters["required"] == ["doc_id"]
    assert '"wait": false' in CompileDocumentTool.spec.description
    # Дольше обычного таймаута клиента MCP (60 с) не ждём.
    assert COMPILE_WAIT_S < 60


@pytest.mark.parametrize("wait", [False, "false"])
async def test__wait_false__returns_compile_id_at_once_without_waiting(tmp_path: Path, wait: object) -> None:
    agent, trigger, compile_id = await _agent_tool(tmp_path, CompileStatus.pending)

    async with asyncio.timeout(1):
        result = await _mcp_tool(agent).handle(_ctx(), {"doc_id": "tz", "wait": wait})

    assert not result.is_error
    assert f"compile_id: {compile_id}" in result.text
    assert "status: in_progress" in result.text
    assert "get_compile" in result.text
    assert trigger.calls == 1


async def test__wait_true__build_outlives_the_limit__in_progress_not_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hse_doc_studio.use_cases.mcp.tools.compile_document.COMPILE_WAIT_S", 0.05)
    agent, _, compile_id = await _agent_tool(tmp_path, CompileStatus.running)

    async with asyncio.timeout(5):
        result = await _mcp_tool(agent).handle(_ctx(), {"doc_id": "tz"})

    assert not result.is_error
    assert result.text.startswith("Сборка tz ещё идёт")
    assert f"compile_id: {compile_id}" in result.text
    assert "Запускать сборку заново не нужно" in result.text


async def test__wait_true__finished_build__full_result_as_for_the_agent(tmp_path: Path) -> None:
    agent, _, _ = await _agent_tool(tmp_path, CompileStatus.success)

    result = await _mcp_tool(agent).handle(_ctx(), {"doc_id": "tz", "wait": True})

    assert not result.is_error
    assert result.text.startswith("Сборка tz: success")


async def test__agent__ignores_wait_and_keeps_its_schema(tmp_path: Path) -> None:
    agent, _, _ = await _agent_tool(tmp_path, CompileStatus.success)

    result = await agent.handle(_ctx(), {"doc_id": "tz", "wait": False})

    assert result.text.startswith("Сборка tz: success")
    assert "wait" not in agent.definition().spec.parameters["properties"]


async def test__with_wait_limit__leaves_the_agent_tool_unchanged(tmp_path: Path) -> None:
    agent, _, _ = await _agent_tool(tmp_path, CompileStatus.running)

    limited = agent.with_wait_limit(0.05)
    result = await limited.handle(_ctx(), {"doc_id": "tz"})

    assert not result.is_error
    assert agent._wait_s > 60  # noqa: SLF001 — копия не трогает ожидание агента
    assert agent._reports_running is False  # noqa: SLF001
