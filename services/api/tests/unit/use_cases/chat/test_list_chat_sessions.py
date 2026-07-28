from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.entities import ChatSession
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat.list_chat_sessions import ListChatSessionsInput, ListChatSessionsUC
from tests.unit.use_cases.chat.conftest import _FakeIndex, _FakeProjects


async def test__execute__one_session_created_none_running__lists_it_with_no_active_ids(
    project_index: _FakeIndex,
    projects: _FakeProjects,
    project_id: UUID,
    chat_repo: JsonChatRepository,
    created_session: ChatSession,
) -> None:
    uc = ListChatSessionsUC(projects, project_index, chat_repo, AgentRunManager())  # type: ignore[arg-type]

    out = await uc.execute(ListChatSessionsInput(project_id=project_id))

    assert [s.id for s in out.sessions] == [created_session.id]
    assert out.active_session_ids == set()
