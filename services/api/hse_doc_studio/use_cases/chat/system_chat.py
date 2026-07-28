from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from hse_doc_studio.core.entities import ChatSession
from hse_doc_studio.core.enums import AgentRunStatus, Lang
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.repositories import IChatRepository
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.use_cases.chat.cancel_chat_turn import CancelChatTurnOutput
from hse_doc_studio.use_cases.chat.create_chat_session import CreateChatSessionOutput
from hse_doc_studio.use_cases.chat.delete_chat_session import DeleteChatSessionOutput
from hse_doc_studio.use_cases.chat.get_chat_session import GetChatSessionOutput
from hse_doc_studio.use_cases.chat.list_chat_sessions import ListChatSessionsOutput
from hse_doc_studio.use_cases.chat.rename_chat_session import RenameChatSessionOutput

# The system (no-project) agent persists its chats in a fixed app-level folder,
# reusing the per-project chat repository/stack against that folder. These UCs
# mirror the project chat CRUD but skip project resolution.

_DEFAULT_TITLE = {Lang.ru: "Новый чат", Lang.en: "New chat"}
_CANCELLED_NO_TASK = {Lang.ru: "отменено (нет активной задачи)", Lang.en: "cancelled (no active task)"}
_TERMINAL = (AgentRunStatus.succeeded, AgentRunStatus.failed, AgentRunStatus.cancelled, AgentRunStatus.interrupted)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SystemListChatSessionsUC:
    def __init__(self, folder: Path, chat_repo: IChatRepository, run_manager: AgentRunManager) -> None:
        self._folder = folder
        self._chat_repo = chat_repo
        self._run_manager = run_manager

    async def execute(self) -> ListChatSessionsOutput:
        sessions = self._chat_repo.list_sessions(self._folder)
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        active = {s.id for s in sessions if self._run_manager.active_run_for_session(s.id) is not None}
        return ListChatSessionsOutput(sessions=sessions, active_session_ids=active)


class SystemCreateChatSessionUC:
    def __init__(self, folder: Path, chat_repo: IChatRepository) -> None:
        self._folder = folder
        self._chat_repo = chat_repo

    async def execute(
        self,
        title: str | None = None,
        default_provider_id: UUID | None = None,
        default_model: str | None = None,
        project_id: UUID | None = None,
        persona: str | None = None,
        persona_instructions: str | None = None,
    ) -> CreateChatSessionOutput:
        now = _now()
        session = ChatSession(
            id=uuid4(),
            project_folder=self._folder,
            title=(title or "").strip() or _DEFAULT_TITLE.get(current_interface_language(), _DEFAULT_TITLE[Lang.ru]),
            doc_id=None,
            project_id=project_id,
            created_at=now,
            updated_at=now,
            default_provider_id=default_provider_id,
            default_model=default_model,
            persona=persona,
            persona_instructions=persona_instructions,
        )
        self._chat_repo.save_session(session)
        return CreateChatSessionOutput(session=session)


class SystemGetChatSessionUC:
    def __init__(self, folder: Path, chat_repo: IChatRepository, run_manager: AgentRunManager) -> None:
        self._folder = folder
        self._chat_repo = chat_repo
        self._run_manager = run_manager

    async def execute(self, session_id: UUID) -> GetChatSessionOutput:
        session = self._chat_repo.get_session(self._folder, session_id)
        if session is None:
            raise NotFoundError(
                localized_error(f"Сессия чата {session_id!r} не найдена", f"Chat session {session_id!r} not found")
            )
        messages = self._chat_repo.list_messages(self._folder, session_id)
        active_run_id = self._run_manager.active_run_for_session(session_id)
        return GetChatSessionOutput(session=session, messages=messages, active_run_id=active_run_id)


class SystemRenameChatSessionUC:
    def __init__(self, folder: Path, chat_repo: IChatRepository) -> None:
        self._folder = folder
        self._chat_repo = chat_repo

    async def execute(
        self,
        session_id: UUID,
        title: str | None = None,
        persona: str | None = None,
        persona_instructions: str | None = None,
    ) -> RenameChatSessionOutput:
        session = self._chat_repo.get_session(self._folder, session_id)
        if session is None:
            raise NotFoundError(
                localized_error(f"Сессия чата {session_id!r} не найдена", f"Chat session {session_id!r} not found")
            )
        if title is not None:
            clean = title.strip()
            if not clean:
                raise ValueError(localized_error("Название обязательно", "Title is required"))
            session.title = clean
        if persona is not None:
            session.persona = persona
            session.persona_instructions = persona_instructions
        session.updated_at = _now()
        self._chat_repo.save_session(session)
        return RenameChatSessionOutput(session=session)


class SystemDeleteChatSessionUC:
    def __init__(self, folder: Path, chat_repo: IChatRepository, run_manager: AgentRunManager) -> None:
        self._folder = folder
        self._chat_repo = chat_repo
        self._run_manager = run_manager

    async def execute(self, session_id: UUID) -> DeleteChatSessionOutput:
        if self._run_manager.active_run_for_session(session_id) is not None:
            raise PermissionError("a turn is currently running in this chat")
        deleted = self._chat_repo.delete_session(self._folder, session_id)
        return DeleteChatSessionOutput(deleted=deleted)


class SystemCancelChatTurnUC:
    def __init__(
        self,
        folder: Path,
        chat_repo: IChatRepository,
        bus: AgentRunBus,
        run_manager: AgentRunManager,
    ) -> None:
        self._folder = folder
        self._chat_repo = chat_repo
        self._bus = bus
        self._run_manager = run_manager

    async def execute(self, run_id: UUID) -> CancelChatTurnOutput:
        if self._run_manager.is_running(run_id):
            await self._run_manager.cancel(run_id)
            return CancelChatTurnOutput(cancelled_task=True, record_finalized=False)
        run = self._chat_repo.get_run(self._folder, run_id)
        if run is None:
            raise NotFoundError(localized_error(f"Запуск {run_id!r} не найден", f"Run {run_id!r} not found"))
        if run.status in _TERMINAL:
            return CancelChatTurnOutput(cancelled_task=False, record_finalized=False)
        run.status = AgentRunStatus.cancelled
        run.finished_at = _now()
        run.error = _CANCELLED_NO_TASK.get(current_interface_language(), _CANCELLED_NO_TASK[Lang.ru])
        self._chat_repo.save_run(run)
        self._bus.close(run_id)
        self._bus.discard(run_id)
        return CancelChatTurnOutput(cancelled_task=False, record_finalized=True)
