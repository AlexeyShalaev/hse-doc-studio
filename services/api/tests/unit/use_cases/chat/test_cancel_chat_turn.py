from __future__ import annotations

from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.entities import AgentRunRecord
from hse_doc_studio.core.enums import AgentRunStatus
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat.cancel_chat_turn import CancelChatTurnInput, CancelChatTurnUC
from tests.unit.use_cases.chat.conftest import _FakeIndex, _FakeProjects


async def test__execute__no_live_task_for_run__force_finalizes_orphan_run(
    tmp_path: Path,
    project_index: _FakeIndex,
    projects: _FakeProjects,
    project_id: UUID,
    chat_repo: JsonChatRepository,
    running_run: AgentRunRecord,
) -> None:
    uc = CancelChatTurnUC(projects, project_index, chat_repo, AgentRunBus(), AgentRunManager())  # type: ignore[arg-type]

    out = await uc.execute(
        CancelChatTurnInput(project_id=project_id, session_id=running_run.session_id, run_id=running_run.id)
    )

    assert out.cancelled_task is False
    assert out.record_finalized is True
    finalized = chat_repo.get_run(tmp_path, running_run.id)
    assert finalized is not None
    assert finalized.status == AgentRunStatus.cancelled
