"""Тела запросов к модели в памяти api: в очередь они не пишутся (промпт с исходниками не хранится в базе)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from hse_doc_studio.core.jobs.enums import JobKind

if TYPE_CHECKING:
    from hse_doc_studio.core.jobs.queue import QueuedJob
    from hse_doc_studio.core.jobs.relay import IRelayHub


@dataclass(frozen=True)
class StoredRelayRequest:
    body: bytes = field(repr=False)
    sha256: str
    user_id: str
    runner_id: str


class RelayRequestStore:
    """Живёт до конца ретрансляции; заодно считает идущие и ждущие ретрансляции каждого человека."""

    def __init__(self) -> None:
        self._requests: dict[UUID, StoredRelayRequest] = {}

    def put(self, job_id: UUID, body: bytes, *, user_id: str, runner_id: str) -> StoredRelayRequest:
        stored = StoredRelayRequest(
            body=body, sha256=hashlib.sha256(body).hexdigest(), user_id=user_id, runner_id=runner_id
        )
        self._requests[job_id] = stored
        return stored

    def get(self, job_id: UUID) -> StoredRelayRequest | None:
        return self._requests.get(job_id)

    def drop(self, job_id: UUID) -> None:
        self._requests.pop(job_id, None)

    def pending_for(self, user_id: str) -> int:
        return sum(1 for stored in self._requests.values() if stored.user_id == user_id)

    def bytes_for(self, user_id: str) -> int:
        return sum(len(stored.body) for stored in self._requests.values() if stored.user_id == user_id)

    def pending_total(self) -> int:
        """Сколько ретрансляций живёт в процессе: у каждой свой канал с буфером порций."""
        return len(self._requests)

    def bytes_total(self) -> int:
        return sum(len(stored.body) for stored in self._requests.values())


class RelayTerminalCleanup:
    """Слушатель терминального состояния: тело и канал уходят из памяти, даже если потребитель не закрыл поток.

    Обычно их освобождает сам поток (`release`, `abort`), но брошенный без `aclose` ответ (отмена задачи
    asyncio посреди чтения) оставил бы тело в памяти до рестарта api и навсегда занял бы место в пределе
    `RELAY_MAX_PENDING_PER_USER`. Регистрируется после `RelayHub`, чтобы тот успел оборвать поток с кодом задачи.
    """

    def __init__(self, hub: IRelayHub, store: RelayRequestStore) -> None:
        self._hub = hub
        self._store = store

    async def on_terminal(self, job: QueuedJob) -> None:
        if job.kind is not JobKind.ai_relay:
            return
        self._store.drop(job.id)
        self._hub.discard(job.id)
