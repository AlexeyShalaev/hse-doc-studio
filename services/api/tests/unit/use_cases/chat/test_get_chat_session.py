from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.entities import ChatSession
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat.get_chat_session import GetChatSessionInput, GetChatSessionUC
from tests.unit.use_cases.chat.conftest import _FakeIndex, _FakeProjects


async def test__execute__existing_session_no_run__returns_session_with_no_active_run_and_empty_messages(
    project_index: _FakeIndex,
    projects: _FakeProjects,
    project_id: UUID,
    chat_repo: JsonChatRepository,
    created_session: ChatSession,
) -> None:
    uc = GetChatSessionUC(projects, project_index, chat_repo, AgentRunManager())  # type: ignore[arg-type]

    out = await uc.execute(GetChatSessionInput(project_id=project_id, session_id=created_session.id))

    assert out.session.title == "My chat"
    assert out.active_run_id is None
    assert out.messages == []
