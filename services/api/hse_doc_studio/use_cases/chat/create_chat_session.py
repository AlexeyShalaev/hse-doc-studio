from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from hse_doc_studio.core.entities import ChatSession
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    IChatRepository,
)

# Resolved at creation against the interface language, then stored on the session.
_DEFAULT_TITLE = {Lang.ru: "Новый чат", Lang.en: "New chat"}


@dataclass
class CreateChatSessionInput:
    project_id: UUID
    title: str | None = None
    doc_id: str | None = None
    default_provider_id: UUID | None = None
    default_model: str | None = None
    persona: str | None = None
    persona_instructions: str | None = None


@dataclass
class CreateChatSessionOutput:
    session: ChatSession


class CreateChatSessionUC:
    def __init__(
        self,
        locator: IProjectLocator,
        chat_repo: IChatRepository,
    ) -> None:
        self._locator = locator
        self._chat_repo = chat_repo

    async def execute(self, inp: CreateChatSessionInput) -> CreateChatSessionOutput:
        folder = await self._locator.folder_of(inp.project_id)
        if folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id!r} не найден", f"Project {inp.project_id!r} not found")
            )
        now = datetime.now(timezone.utc)
        lang = current_interface_language()
        title = (inp.title or "").strip() or _DEFAULT_TITLE.get(lang, _DEFAULT_TITLE[Lang.ru])
        session = ChatSession(
            id=uuid4(),
            project_folder=folder,
            title=title,
            doc_id=inp.doc_id,
            created_at=now,
            updated_at=now,
            default_provider_id=inp.default_provider_id,
            default_model=inp.default_model,
            persona=inp.persona,
            persona_instructions=inp.persona_instructions,
        )
        self._chat_repo.save_session(session)
        return CreateChatSessionOutput(session=session)
