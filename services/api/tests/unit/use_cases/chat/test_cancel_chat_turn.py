from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.entities import AgentRunRecord
from hse_doc_studio.core.enums import AgentEventType, AgentRunStatus
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat.cancel_chat_turn import CancelChatTurnInput, CancelChatTurnUC
from hse_doc_studio.use_cases.chat.get_chat_run_stream import GetChatRunStreamInput, GetChatRunStreamUC
from hse_doc_studio.use_cases.chat.system_chat import SystemCancelChatTurnUC
from hse_doc_studio.use_cases.chat.system_get_chat_run_stream import SystemGetChatRunStreamUC
from tests.unit.use_cases.chat.conftest import _FakeLocator


async def test__execute__no_live_task_for_run__force_finalizes_orphan_run(
    tmp_path: Path,
    locator: _FakeLocator,
    project_id: UUID,
    chat_repo: JsonChatRepository,
    running_run: AgentRunRecord,
) -> None:
    uc = CancelChatTurnUC(locator, chat_repo, AgentRunBus(), AgentRunManager())  # type: ignore[arg-type]

    out = await uc.execute(
        CancelChatTurnInput(project_id=project_id, session_id=running_run.session_id, run_id=running_run.id)
    )

    assert out.cancelled_task is False
    assert out.record_finalized is True
    finalized = await chat_repo.get_run(tmp_path, running_run.id)
    assert finalized is not None
    assert finalized.status == AgentRunStatus.cancelled


async def test__execute__run_of_another_session__not_found_and_not_cancelled(
    locator: _FakeLocator,
    project_id: UUID,
    chat_repo: JsonChatRepository,
    running_run: AgentRunRecord,
) -> None:
    manager = AgentRunManager()
    manager.cancel = AsyncMock()  # type: ignore[method-assign]
    manager.is_running = lambda _run_id: True  # type: ignore[method-assign]
    uc = CancelChatTurnUC(locator, chat_repo, AgentRunBus(), manager)  # type: ignore[arg-type]

    with pytest.raises(NotFoundError):
        await uc.execute(CancelChatTurnInput(project_id=project_id, session_id=uuid4(), run_id=running_run.id))

    manager.cancel.assert_not_awaited()


async def test__system_cancel__run_of_another_session__not_found_and_not_cancelled(
    tmp_path: Path, chat_repo: JsonChatRepository, running_run: AgentRunRecord
) -> None:
    manager = AgentRunManager()
    manager.cancel = AsyncMock()  # type: ignore[method-assign]
    manager.is_running = lambda _run_id: True  # type: ignore[method-assign]
    uc = SystemCancelChatTurnUC(tmp_path, chat_repo, AgentRunBus(), manager)

    with pytest.raises(NotFoundError):
        await uc.execute(uuid4(), running_run.id)
    manager.cancel.assert_not_awaited()

    assert (await uc.execute(running_run.session_id, running_run.id)).cancelled_task is True


async def test__stream__run_of_another_session__never_touches_the_bus(
    tmp_path: Path,
    locator: _FakeLocator,
    project_id: UUID,
    chat_repo: JsonChatRepository,
    running_run: AgentRunRecord,
) -> None:
    bus = MagicMock()
    bus.has.return_value = True

    project_uc = GetChatRunStreamUC(locator, chat_repo, bus)  # type: ignore[arg-type]
    system_uc = SystemGetChatRunStreamUC(tmp_path, chat_repo, bus)
    streams = [
        await project_uc.execute(GetChatRunStreamInput(project_id, uuid4(), running_run.id)),
        await system_uc.execute(uuid4(), running_run.id),
    ]

    for stream in streams:
        events = [e async for e in stream]
        assert [(e.type, e.data["message"]) for e in events] == [(AgentEventType.error, "run not found")]
    bus.has.assert_not_called()
    bus.subscribe.assert_not_called()
