from __future__ import annotations

from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.entities import ChatSession
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat.delete_chat_session import DeleteChatSessionInput, DeleteChatSessionUC
from tests.unit.use_cases.chat.conftest import _FakeIndex, _FakeProjects


async def test__execute__existing_session__deletes_it_from_the_repo(
    tmp_path: Path,
    project_index: _FakeIndex,
    projects: _FakeProjects,
    project_id: UUID,
    chat_repo: JsonChatRepository,
    created_session: ChatSession,
) -> None:
    uc = DeleteChatSessionUC(projects, project_index, chat_repo, AgentRunManager())  # type: ignore[arg-type]

    out = await uc.execute(DeleteChatSessionInput(project_id=project_id, session_id=created_session.id))

    assert out.deleted is True
    assert chat_repo.get_session(tmp_path, created_session.id) is None
