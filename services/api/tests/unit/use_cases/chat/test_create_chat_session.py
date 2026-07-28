from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat.create_chat_session import CreateChatSessionInput, CreateChatSessionUC
from tests.unit.use_cases.chat.conftest import _FakeIndex, _FakeProjects


async def test__execute__known_project__creates_session_with_title_and_doc(
    chat_repo: JsonChatRepository, project_index: _FakeIndex, projects: _FakeProjects, project_id: UUID
) -> None:
    uc = CreateChatSessionUC(projects, project_index, chat_repo)  # type: ignore[arg-type]

    out = await uc.execute(CreateChatSessionInput(project_id=project_id, title="My chat", doc_id="vkr"))

    assert out.session.title == "My chat"
    assert out.session.doc_id == "vkr"


async def test__execute__unknown_project__raises_not_found(
    chat_repo: JsonChatRepository, tmp_path: Path, project_index: _FakeIndex
) -> None:
    projects = _FakeProjects(tmp_path, uuid4())
    uc = CreateChatSessionUC(projects, project_index, chat_repo)  # type: ignore[arg-type]

    with pytest.raises(NotFoundError, match="не найден"):
        await uc.execute(CreateChatSessionInput(project_id=uuid4()))
