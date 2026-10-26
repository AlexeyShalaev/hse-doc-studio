from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID


class IEventBus[T](Protocol):
    # In-memory pub/sub keyed by a topic id. Replay-from-start is the contract:
    # a late subscriber first gets everything already published, then live
    # events, and the iterator ends once the topic is closed. `publish` is sync
    # on purpose (callers are sync closures and stream sinks) and is ignored
    # after `close`. `subscribe` is a plain def returning an async iterator so
    # async-generator implementations match it.
    def publish(self, topic: UUID, event: T, /) -> None: ...
    def close(self, topic: UUID, /) -> None: ...
    def discard(self, topic: UUID, /) -> None: ...
    def has(self, topic: UUID, /) -> bool: ...
    def subscribe(self, topic: UUID, /) -> AsyncIterator[T]: ...


class IJobLogStream(IEventBus[str], Protocol):
    # Live log lines of a background job, topic = job id.
    ...
