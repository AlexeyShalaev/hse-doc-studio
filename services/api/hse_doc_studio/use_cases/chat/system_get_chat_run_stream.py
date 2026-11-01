from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.agent.entities import AgentEvent
from hse_doc_studio.core.agent.protocols import IAgentRunBus
from hse_doc_studio.core.entities import AgentRunRecord
from hse_doc_studio.core.enums import AgentEventType, AgentRunStatus
from hse_doc_studio.core.repositories import IChatRepository
from hse_doc_studio.use_cases.chat.run_channel import CHANNEL_WAIT_S, await_run_channel

_TERMINAL = (
    AgentRunStatus.succeeded,
    AgentRunStatus.failed,
    AgentRunStatus.cancelled,
    AgentRunStatus.interrupted,
    AgentRunStatus.awaiting_approval,
)


class SystemGetChatRunStreamUC:
    """System-scope twin of GetChatRunStreamUC: live bus events, then backfill +
    terminal event, against a fixed app-level folder (no project resolution)."""

    def __init__(
        self,
        folder: Path,
        chat_repo: IChatRepository,
        bus: IAgentRunBus,
        *,
        channel_wait_s: float = CHANNEL_WAIT_S,
    ) -> None:
        self._folder = folder
        self._chat_repo = chat_repo
        self._bus = bus
        self._channel_wait_s = channel_wait_s

    async def execute(self, session_id: UUID, run_id: UUID) -> AsyncGenerator[AgentEvent, None]:
        # Чужой запуск (другая сессия) не должен ни подписываться на шину, ни показывать события.
        owned = await self._chat_repo.get_run(self._folder, run_id)
        if owned is None or owned.session_id != session_id:
            return self._error_stream()
        return self._stream(session_id, run_id)

    @staticmethod
    def _error_stream() -> AsyncGenerator[AgentEvent, None]:
        async def _gen() -> AsyncGenerator[AgentEvent, None]:
            yield AgentEvent(type=AgentEventType.error, data={"status": "failed", "message": "run not found"})

        return _gen()

    def _stream(  # noqa: C901 — live-then-backfill stream state machine, like GetChatRunStreamUC
        self, session_id: UUID, run_id: UUID
    ) -> AsyncGenerator[AgentEvent, None]:
        bus = self._bus
        chat_repo = self._chat_repo
        folder = self._folder
        backfill = self._backfill_messages
        wait_s = self._channel_wait_s

        async def _gen() -> AsyncGenerator[AgentEvent, None]:
            seen_live = False
            # Запуск мог быть принят только что: канал шины откроет его фоновая задача.
            await await_run_channel(bus, chat_repo, folder, run_id, timeout_s=wait_s)
            if bus.has(run_id):
                async for event in bus.subscribe(run_id):
                    seen_live = True
                    yield event

            run = await chat_repo.get_run(folder, run_id)
            if run is None:
                if not seen_live:
                    yield AgentEvent(type=AgentEventType.error, data={"status": "failed", "message": "run not found"})
                return

            if not seen_live:
                for event in await backfill(session_id, run_id):
                    yield event
            yield _terminal_event(run)

        return _gen()

    async def _backfill_messages(self, session_id: UUID, run_id: UUID) -> list[AgentEvent]:
        return [
            AgentEvent(
                type=AgentEventType.message,
                data={"id": str(m.id), "seq": m.seq, "role": m.role.value},
            )
            for m in await self._chat_repo.list_messages(self._folder, session_id)
            if m.run_id == run_id and m.role.value in ("assistant", "tool")
        ]


def _terminal_event(run: AgentRunRecord) -> AgentEvent:
    status = run.status.value if run.status in _TERMINAL else "failed"
    data: dict[str, object] = {"status": status, "run_id": str(run.id)}
    if run.error:
        data["message"] = run.error
    if run.error_code:
        data["code"] = run.error_code
    if run.usage is not None:
        data["usage"] = {
            "input_tokens": run.usage.input_tokens,
            "output_tokens": run.usage.output_tokens,
            "total_tokens": run.usage.total_tokens,
        }
    return AgentEvent(type=AgentEventType.done, data=data)
