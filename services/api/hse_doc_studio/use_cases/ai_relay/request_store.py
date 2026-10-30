"""Тела запросов к модели в памяти api: в очередь они не пишутся (промпт с исходниками не хранится в базе)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from uuid import UUID


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
