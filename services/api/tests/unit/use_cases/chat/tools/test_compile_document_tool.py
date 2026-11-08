"""compile_document: сборку некому взять, и инструмент говорит почему, а не падает."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.errors import NoRunnerAvailableError
from hse_doc_studio.core.jobs.runner_fit import PoolState, RunnerFit
from hse_doc_studio.use_cases.chat.tools.compile_document import CompileDocumentTool


async def test__compile_document__no_suitable_runner__error_names_the_reason() -> None:
    set_interface_language("ru")
    trigger = MagicMock()
    fit = RunnerFit(tags=frozenset({"office"}), shared=PoolState.absent, personal=PoolState.paused)
    trigger.execute = AsyncMock(side_effect=NoRunnerAvailableError(frozenset({"office"}), any_runner=True, fit=fit))
    tool = CompileDocumentTool(trigger, MagicMock(), MagicMock())
    ctx = AgentToolContext(project_id=uuid4(), model="m", edit_format=EditFormat.search_replace)

    result = await tool.handle(ctx, {"doc_id": "presentation"})

    assert result.is_error
    assert result.text.startswith("[no_runner_for_tags] Нет раннера в сети, который умеет office")
    assert "личный раннер владельца на паузе" in result.text
