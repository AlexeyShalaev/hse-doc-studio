from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class _Channel:
    lines: list[str] = field(default_factory=list)
    done: bool = False
    # Single event woken on every publish so all subscribers re-check len(lines)
    # and either consume new lines or notice that done==True.
    event: asyncio.Event = field(default_factory=asyncio.Event)


class CompileLogBus:
    """In-memory pub/sub for live compile log lines.

    Producer (TriggerCompileUC._run_compile_task) calls publish() on each line
    and close() when the build finishes. Subscribers (GetCompileStreamUC) get
    an AsyncIterator that replays everything already buffered, then waits for
    more, exiting cleanly once close() has been called.
    """

    def __init__(self) -> None:
        self._channels: dict[UUID, _Channel] = {}

    def publish(self, compile_id: UUID, line: str) -> None:
        chan = self._channels.setdefault(compile_id, _Channel())
        if chan.done:
            return
        chan.lines.append(line)
        chan.event.set()

    def close(self, compile_id: UUID) -> None:
        chan = self._channels.setdefault(compile_id, _Channel())
        chan.done = True
        chan.event.set()

    def discard(self, compile_id: UUID) -> None:
        self._channels.pop(compile_id, None)

    def has(self, compile_id: UUID) -> bool:
        return compile_id in self._channels

    async def subscribe(self, compile_id: UUID) -> AsyncIterator[str]:
        chan = self._channels.setdefault(compile_id, _Channel())
        cursor = 0
        while True:
            if cursor < len(chan.lines):
                yield chan.lines[cursor]
                cursor += 1
                continue
            if chan.done:
                return
            chan.event.clear()
            await chan.event.wait()
