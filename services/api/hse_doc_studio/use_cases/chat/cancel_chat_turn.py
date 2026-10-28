from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from hse_doc_studio.core.agent.protocols import IAgentRunBus
from hse_doc_studio.core.enums import AgentRunStatus, Lang
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    IChatRepository,
)
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager

_TERMINAL = (AgentRunStatus.succeeded, AgentRunStatus.failed, AgentRunStatus.cancelled, AgentRunStatus.interrupted)
_CANCELLED_NO_TASK = {Lang.ru: "отменено (нет активной задачи)", Lang.en: "cancelled (no active task)"}


@dataclass
class CancelChatTurnInput:
    project_id: UUID
    session_id: UUID
    run_id: UUID


@dataclass
class CancelChatTurnOutput:
    cancelled_task: bool
    record_finalized: bool


class CancelChatTurnUC:
    def __init__(
        self,
        locator: IProjectLocator,
        chat_repo: IChatRepository,
        bus: IAgentRunBus,
        run_manager: AgentRunManager,
    ) -> None:
        self._locator = locator
        self._chat_repo = chat_repo
        self._bus = bus
        self._run_manager = run_manager

    async def execute(self, inp: CancelChatTurnInput) -> CancelChatTurnOutput:
        folder = await self._locator.folder_of(inp.project_id)
        if folder is None:
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id!r} не найден", f"Project {inp.project_id!r} not found")
            )

        # Live task: cancel it; the run task itself finalizes the record + bus.
        if self._run_manager.is_running(inp.run_id):
            await self._run_manager.cancel(inp.run_id)
            return CancelChatTurnOutput(cancelled_task=True, record_finalized=False)

        # No live task: force-finalize a record stuck non-terminal (e.g. lost task).
        run = self._chat_repo.get_run(folder, inp.run_id)
        if run is None:
            raise NotFoundError(localized_error(f"Запуск {inp.run_id!r} не найден", f"Run {inp.run_id!r} not found"))
        if run.status in _TERMINAL:
            return CancelChatTurnOutput(cancelled_task=False, record_finalized=False)
        run.status = AgentRunStatus.cancelled
        run.finished_at = datetime.now(timezone.utc)
        run.error = _CANCELLED_NO_TASK.get(current_interface_language(), _CANCELLED_NO_TASK[Lang.ru])
        self._chat_repo.save_run(run)
        self._bus.close(inp.run_id)
        self._bus.discard(inp.run_id)
        return CancelChatTurnOutput(cancelled_task=False, record_finalized=True)
