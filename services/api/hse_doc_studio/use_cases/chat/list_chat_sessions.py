from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from hse_doc_studio.core.entities import ChatSession
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IChatRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.use_cases.chat._support import find_project_folder


@dataclass
class ListChatSessionsInput:
    project_id: UUID


@dataclass
class ListChatSessionsOutput:
    sessions: list[ChatSession]
    # Session ids with an in-flight agent run right now — powers a live
    # "running" indicator across chats so parallel agent activity is visible.
    active_session_ids: set[UUID] = field(default_factory=set)


class ListChatSessionsUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        run_manager: AgentRunManager,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._chat_repo = chat_repo
        self._run_manager = run_manager

    async def execute(self, inp: ListChatSessionsInput) -> ListChatSessionsOutput:
        folder = find_project_folder(inp.project_id, self._project_repo, self._project_index_repo)
        if folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id!r} не найден", f"Project {inp.project_id!r} not found")
            )
        sessions = self._chat_repo.list_sessions(folder)
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        active = {s.id for s in sessions if self._run_manager.active_run_for_session(s.id) is not None}
        return ListChatSessionsOutput(sessions=sessions, active_session_ids=active)
