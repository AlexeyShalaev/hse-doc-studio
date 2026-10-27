from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.entities import ChatSession
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat.rename_chat_session import RenameChatSessionInput, RenameChatSessionUC
from tests.unit.use_cases.chat.conftest import _FakeLocator


async def test__execute__existing_session__title_updated(
    locator: _FakeLocator,
    project_id: UUID,
    chat_repo: JsonChatRepository,
    created_session: ChatSession,
) -> None:
    uc = RenameChatSessionUC(locator, chat_repo)  # type: ignore[arg-type]

    out = await uc.execute(
        RenameChatSessionInput(project_id=project_id, session_id=created_session.id, title="Renamed")
    )

    assert out.session.title == "Renamed"
