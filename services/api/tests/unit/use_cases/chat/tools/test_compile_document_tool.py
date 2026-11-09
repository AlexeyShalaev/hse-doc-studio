"""compile_document: ждёт итог сборки, а при остановке сервера отвечает сразу и говорит, что будет со сборкой.

Сборку некому взять (нет раннера с тегом, личный раннер на паузе): инструмент называет причину, а не падает.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.compile.failure import INTERRUPTED
from hse_doc_studio.core.enums import CompileStatus, EditFormat
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.errors import NoRunnerAvailableError
from hse_doc_studio.core.jobs.runner_fit import PoolState, RunnerFit
from hse_doc_studio.core.shutdown import ServerRestartingError, ShutdownSignal
from hse_doc_studio.use_cases.chat.tools.compile_document import CompileDocumentTool
from tests.contract.test_compile_contract import make_record
from tests.fakes.compile import InMemoryCompileRepository


class Trigger:
    def __init__(self, compile_id: UUID) -> None:
        self.compile_id = compile_id

    async def execute(self, _input: Any) -> SimpleNamespace:
        return SimpleNamespace(compile_id=self.compile_id)


class Projects:
    def __init__(self, folder: Path) -> None:
        self.folder = folder

    async def execute(self, _input: Any) -> SimpleNamespace:
        return SimpleNamespace(project=SimpleNamespace(folder=self.folder))


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=uuid4(), model="mcp-client", edit_format=EditFormat.search_replace)


async def _tool(
    tmp_path: Path, status: CompileStatus, *, survives: bool, shutdown: ShutdownSignal, **changes: Any
) -> tuple[CompileDocumentTool, UUID]:
    compiles = InMemoryCompileRepository()
    record = replace(make_record(tmp_path, doc_id="tz", status=status, **changes))
    await compiles.save(record)
    tool = CompileDocumentTool(
        Trigger(record.id),  # type: ignore[arg-type]
        Projects(tmp_path),  # type: ignore[arg-type]
        compiles,
        shutdown=shutdown,
        builds_survive_restart=survives,
    )
    return tool, record.id


@pytest.fixture(autouse=True)
def _russian() -> None:
    set_interface_language("ru")


async def test__server_stops_while_cloud_build_runs__answers_at_once_that_the_build_continues(tmp_path: Path) -> None:
    shutdown = ShutdownSignal()
    tool, compile_id = await _tool(tmp_path, CompileStatus.running, survives=True, shutdown=shutdown, finished_at=None)
    call = asyncio.create_task(tool.handle(_ctx(), {"doc_id": "tz"}))
    await asyncio.sleep(0.05)

    shutdown.request()
    with pytest.raises(ServerRestartingError) as caught:
        async with asyncio.timeout(1):
            await call

    text = str(caught.value)
    assert "перезапускается" in text
    assert str(compile_id) in text
    assert "get_compile" in text
    assert "Запускать заново не нужно" in text
    assert caught.value.retry_after_s > 0


async def test__server_stops_during_local_build__says_to_build_again(tmp_path: Path) -> None:
    shutdown = ShutdownSignal()
    shutdown.request()
    tool, _ = await _tool(tmp_path, CompileStatus.pending, survives=False, shutdown=shutdown, finished_at=None)

    with pytest.raises(ServerRestartingError) as caught:
        await tool.handle(_ctx(), {"doc_id": "tz"})

    assert "повторите compile_document" in str(caught.value)


async def test__interrupted_record__reported_as_interrupted_error_not_cancelled(tmp_path: Path) -> None:
    tool, _ = await _tool(
        tmp_path, CompileStatus.cancelled, survives=True, shutdown=ShutdownSignal(), error_code=INTERRUPTED
    )

    result = await tool.handle(_ctx(), {"doc_id": "tz"})

    assert result.is_error
    assert result.text.startswith("Сборка tz: прервана")
    assert "перезапуск" in result.text


async def test__finished_build__result_returned_as_before(tmp_path: Path) -> None:
    tool, _ = await _tool(tmp_path, CompileStatus.success, survives=True, shutdown=ShutdownSignal())

    result = await tool.handle(_ctx(), {"doc_id": "tz"})

    assert not result.is_error
    assert result.text.startswith("Сборка tz: success")


async def test__compile_document__no_suitable_runner__error_names_the_reason() -> None:
    trigger = MagicMock()
    fit = RunnerFit(tags=frozenset({"office"}), shared=PoolState.absent, personal=PoolState.paused)
    trigger.execute = AsyncMock(side_effect=NoRunnerAvailableError(frozenset({"office"}), any_runner=True, fit=fit))
    tool = CompileDocumentTool(trigger, MagicMock(), MagicMock())

    result = await tool.handle(_ctx(), {"doc_id": "presentation"})

    assert result.is_error
    assert result.text.startswith("[no_runner_for_tags] Нет раннера в сети, который умеет office")
    assert "личный раннер владельца на паузе" in result.text
