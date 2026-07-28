from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.agent.entities import AgentEvent
from hse_doc_studio.core.entities import AgentRunRecord
from hse_doc_studio.core.enums import AgentEventType, AgentRunStatus
from hse_doc_studio.core.repositories import (
    IChatRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.infra.ai.agent.run_bus import AgentRunBus
from hse_doc_studio.use_cases.chat._support import find_project_folder

logger = structlog.get_logger()

_TERMINAL = (
    AgentRunStatus.succeeded,
    AgentRunStatus.failed,
    AgentRunStatus.cancelled,
    AgentRunStatus.interrupted,
    AgentRunStatus.awaiting_approval,  # a pause, but the stream ends and reports it
)


@dataclass
class GetChatRunStreamInput:
    project_id: UUID
    session_id: UUID
    run_id: UUID


class GetChatRunStreamUC:
    """Yield run events: live from the bus while active, then a terminal event.

    A late subscriber (run already finished, bus discarded) gets the run's
    persisted messages replayed as `message` events followed by the terminal
    event derived from the run record (mirrors GetCompileStreamUC's backfill).
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        chat_repo: IChatRepository,
        bus: AgentRunBus,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._chat_repo = chat_repo
        self._bus = bus

    async def execute(self, inp: GetChatRunStreamInput) -> AsyncGenerator[AgentEvent, None]:
        folder = find_project_folder(inp.project_id, self._project_repo, self._project_index_repo)
        if folder is None:
            return self._error_stream("project not found")
        return self._stream(folder, inp.session_id, inp.run_id)

    def _error_stream(self, message: str) -> AsyncGenerator[AgentEvent, None]:
        async def _gen() -> AsyncGenerator[AgentEvent, None]:
            yield AgentEvent(type=AgentEventType.error, data={"status": "failed", "message": message})

        return _gen()

    def _stream(  # noqa: C901 — live-then-backfill stream state machine, like GetCompileStreamUC
        self, folder: Path, session_id: UUID, run_id: UUID
    ) -> AsyncGenerator[AgentEvent, None]:
        bus = self._bus
        chat_repo = self._chat_repo
        backfill = self._backfill_messages
        terminal = self._terminal_event

        async def _gen() -> AsyncGenerator[AgentEvent, None]:
            seen_live = False
            if bus.has(run_id):
                async for event in bus.subscribe(run_id):
                    seen_live = True
                    yield event

            run = chat_repo.get_run(folder, run_id)
            if run is None:
                if not seen_live:
                    yield AgentEvent(type=AgentEventType.error, data={"status": "failed", "message": "run not found"})
                return

            if not seen_live:
                for event in backfill(folder, session_id, run_id):
                    yield event
            yield terminal(run)

        return _gen()

    def _backfill_messages(self, folder: Path, session_id: UUID, run_id: UUID) -> list[AgentEvent]:
        # Replay a finished run's messages as `message` events for a late subscriber.
        return [
            AgentEvent(
                type=AgentEventType.message,
                data={"id": str(m.id), "seq": m.seq, "role": m.role.value},
            )
            for m in self._chat_repo.list_messages(folder, session_id)
            if m.run_id == run_id and m.role.value in ("assistant", "tool")
        ]

    @staticmethod
    def _terminal_event(run: AgentRunRecord) -> AgentEvent:
        status = run.status.value if run.status in _TERMINAL else "failed"
        data: dict[str, object] = {"status": status, "run_id": str(run.id)}
        if run.error:
            data["message"] = run.error
        if run.usage is not None:
            data["usage"] = {
                "input_tokens": run.usage.input_tokens,
                "output_tokens": run.usage.output_tokens,
                "total_tokens": run.usage.total_tokens,
            }
        return AgentEvent(type=AgentEventType.done, data=data)
