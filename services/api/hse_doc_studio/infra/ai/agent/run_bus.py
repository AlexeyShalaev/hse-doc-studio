from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID

from hse_doc_studio.core.agent.entities import AgentEvent


@dataclass
class _Channel:
    events: list[AgentEvent] = field(default_factory=list)
    done: bool = False
    # One event woken on every publish so all subscribers re-check len(events)
    # and either consume new events or notice done==True.
    wakeup: asyncio.Event = field(default_factory=asyncio.Event)


class AgentRunBus:
    """In-memory pub/sub for live agent-run events (typed-event twin of CompileLogBus).

    The run task (StartChatTurnUC._run_turn_task) publishes AgentEvents as they
    occur and closes the channel when the turn ends. The stream use case
    subscribes, replays buffered events, then waits for more, exiting once the
    channel is closed. App-scoped singleton so a run outlives the request that
    started it.
    """

    def __init__(self) -> None:
        self._channels: dict[UUID, _Channel] = {}

    def publish(self, run_id: UUID, event: AgentEvent) -> None:
        chan = self._channels.setdefault(run_id, _Channel())
        if chan.done:
            return
        chan.events.append(event)
        chan.wakeup.set()

    def close(self, run_id: UUID) -> None:
        chan = self._channels.setdefault(run_id, _Channel())
        chan.done = True
        chan.wakeup.set()

    def discard(self, run_id: UUID) -> None:
        self._channels.pop(run_id, None)

    def has(self, run_id: UUID) -> bool:
        return run_id in self._channels

    async def subscribe(self, run_id: UUID) -> AsyncIterator[AgentEvent]:
        chan = self._channels.setdefault(run_id, _Channel())
        cursor = 0
        while True:
            if cursor < len(chan.events):
                yield chan.events[cursor]
                cursor += 1
                continue
            if chan.done:
                return
            chan.wakeup.clear()
            await chan.wakeup.wait()
