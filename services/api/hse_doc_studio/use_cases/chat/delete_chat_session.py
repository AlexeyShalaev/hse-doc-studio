from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    IChatRepository,
)
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager


@dataclass
class DeleteChatSessionInput:
    project_id: UUID
    session_id: UUID


@dataclass
class DeleteChatSessionOutput:
    deleted: bool


class DeleteChatSessionUC:
    def __init__(
        self,
        locator: IProjectLocator,
        chat_repo: IChatRepository,
        run_manager: AgentRunManager,
    ) -> None:
        self._locator = locator
        self._chat_repo = chat_repo
        self._run_manager = run_manager

    async def execute(self, inp: DeleteChatSessionInput) -> DeleteChatSessionOutput:
        folder = await self._locator.folder_of(inp.project_id)
        if folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id!r} не найден", f"Project {inp.project_id!r} not found")
            )
        # Refuse to delete while a turn is live — it would yank the transcript
        # out from under the running task. The API maps this to a 409.
        if self._run_manager.active_run_for_session(inp.session_id) is not None:
            raise PermissionError("a turn is currently running in this chat")
        deleted = await self._chat_repo.delete_session(folder, inp.session_id)
        return DeleteChatSessionOutput(deleted=deleted)
