from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.entities import AgentRunRecord, ChatSession
from hse_doc_studio.core.enums import AgentRunStatus
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat.create_chat_session import CreateChatSessionInput, CreateChatSessionUC


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _FakeIndex:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def list_known(self) -> list[Path]:
        return [self._folder]

    def register(self, folder: Path) -> None: ...

    def unregister(self, folder: Path) -> None: ...


class _FakeProjects:
    def __init__(self, folder: Path, project_id: UUID) -> None:
        self._folder = folder
        self._project_id = project_id

    def get(self, folder: Path) -> object | None:
        return SimpleNamespace(id=self._project_id) if folder == self._folder else None

    def save(self, project: object) -> None: ...


@pytest.fixture
def project_id() -> UUID:
    return uuid4()


@pytest.fixture
def project_index(tmp_path: Path) -> _FakeIndex:
    return _FakeIndex(tmp_path)


@pytest.fixture
def projects(tmp_path: Path, project_id: UUID) -> _FakeProjects:
    return _FakeProjects(tmp_path, project_id)


@pytest.fixture
def chat_repo() -> JsonChatRepository:
    return JsonChatRepository()


@pytest.fixture
async def created_session(
    chat_repo: JsonChatRepository,
    projects: _FakeProjects,
    project_index: _FakeIndex,
    project_id: UUID,
) -> ChatSession:
    """A session persisted through the real create-session use case, title 'My chat'."""
    out = await CreateChatSessionUC(projects, project_index, chat_repo).execute(  # type: ignore[arg-type]
        CreateChatSessionInput(project_id=project_id, title="My chat")
    )
    return out.session


@pytest.fixture
def running_run(chat_repo: JsonChatRepository, tmp_path: Path) -> AgentRunRecord:
    """A session with an in-progress AgentRunRecord, as if a turn were mid-flight."""
    session = ChatSession(
        id=uuid4(), project_folder=tmp_path, title="t", doc_id=None, created_at=_now(), updated_at=_now()
    )
    chat_repo.save_session(session)
    run = AgentRunRecord(
        id=uuid4(),
        session_id=session.id,
        project_folder=tmp_path,
        status=AgentRunStatus.running,
        created_at=_now(),
        started_at=_now(),
        finished_at=None,
        trigger_seq=0,
    )
    chat_repo.save_run(run)
    return run
