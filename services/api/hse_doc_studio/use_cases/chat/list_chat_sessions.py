from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from hse_doc_studio.core.entities import ChatSession
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    IChatRepository,
)
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager


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
        locator: IProjectLocator,
        chat_repo: IChatRepository,
        run_manager: AgentRunManager,
    ) -> None:
        self._locator = locator
        self._chat_repo = chat_repo
        self._run_manager = run_manager

    async def execute(self, inp: ListChatSessionsInput) -> ListChatSessionsOutput:
        folder = await self._locator.folder_of(inp.project_id)
        if folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id!r} не найден", f"Project {inp.project_id!r} not found")
            )
        sessions = await self._chat_repo.list_sessions(folder)
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        active = {s.id for s in sessions if self._run_manager.active_run_for_session(s.id) is not None}
        return ListChatSessionsOutput(sessions=sessions, active_session_ids=active)
