from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from hse_doc_studio.core.entities import ChatSession
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    IChatRepository,
)


@dataclass
class RenameChatSessionInput:
    project_id: UUID
    session_id: UUID
    # Partial update: only the provided fields change. `persona` (when not None)
    # also rewrites `persona_instructions` so switching roles clears stale text.
    title: str | None = None
    persona: str | None = None
    persona_instructions: str | None = None


@dataclass
class RenameChatSessionOutput:
    session: ChatSession


class RenameChatSessionUC:
    def __init__(
        self,
        locator: IProjectLocator,
        chat_repo: IChatRepository,
    ) -> None:
        self._locator = locator
        self._chat_repo = chat_repo

    async def execute(self, inp: RenameChatSessionInput) -> RenameChatSessionOutput:
        folder = await self._locator.folder_of(inp.project_id)
        if folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id!r} не найден", f"Project {inp.project_id!r} not found")
            )
        session = await self._chat_repo.get_session(folder, inp.session_id)
        if session is None:
            raise NotFoundError(
                localized_error(
                    f"Сессия чата {inp.session_id!r} не найдена", f"Chat session {inp.session_id!r} not found"
                )
            )
        if inp.title is not None:
            title = inp.title.strip()
            if not title:
                raise ValueError(localized_error("Название обязательно", "Title is required"))
            session.title = title
        if inp.persona is not None:
            session.persona = inp.persona
            session.persona_instructions = inp.persona_instructions
        session.updated_at = datetime.now(timezone.utc)
        await self._chat_repo.save_session(session)
        return RenameChatSessionOutput(session=session)
