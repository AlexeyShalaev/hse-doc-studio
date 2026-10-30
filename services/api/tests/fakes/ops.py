"""Фейки админки эксплуатации: читатель очереди поверх InMemoryJobQueue, счётчик места, шифр и транзакция."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.jobs.admin import JobAdminFilter, JobAdminPage, QueueStats
from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.storage.usage import StorageUsage

from tests.fakes.job_queue import InMemoryJobQueue


class InMemoryJobAdminReader:
    def __init__(self, queue: InMemoryJobQueue) -> None:
        self._queue = queue

    async def list_jobs(self, flt: JobAdminFilter, *, before_seq: int | None, limit: int) -> JobAdminPage:
        jobs = [
            j
            for j in reversed(await self._queue.list())
            if (flt.state is None or j.state is flt.state)
            and (flt.kind is None or j.kind is flt.kind)
            and (flt.user_id is None or j.user_id == flt.user_id)
            and (flt.project_id is None or j.project_id == flt.project_id)
            and (before_seq is None or j.seq < before_seq)
        ]
        page = jobs[:limit]
        return JobAdminPage(items=tuple(page), next_before_seq=page[-1].seq if len(jobs) > limit and page else None)

    async def stats(self, now: datetime) -> QueueStats:
        jobs = await self._queue.list()
        by_state: dict[JobState, int] = {}
        for job in jobs:
            by_state[job.state] = by_state.get(job.state, 0) + 1
        queued = [j for j in jobs if j.state is JobState.queued]
        return QueueStats(
            by_state=by_state,
            queued_by_class={},
            oldest_queued_at=min((j.queued_at for j in queued), default=None),
        )


class CountingStorageReader:
    def __init__(self) -> None:
        self.reads = 0

    async def read(self, now: datetime) -> StorageUsage:
        self.reads += 1
        return StorageUsage(
            blob_count=self.reads, blob_bytes=10 * self.reads, projects=1, deleted_projects=0, computed_at=now
        )


class ReversingCipher:
    """Шифр для тестов: привязка к aad проверяется, ключ в открытом виде в хранилище не лежит."""

    def encrypt(self, plaintext: Secret, *, aad: str) -> str:
        return f"{aad}|{plaintext.reveal()[::-1]}"

    def decrypt(self, token: str, *, aad: str, legacy_aad: str | None = None) -> Secret:
        stored_aad, _, body = token.rpartition("|")
        assert stored_aad == aad
        return Secret(body[::-1])


class NoopUow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


class InMemoryAIProviderRepository:
    """IAIProviderRepository без шифрования: как у сервера, пустой ключ при обновлении оставляет прежний."""

    def __init__(self) -> None:
        self._items: dict[UUID, AIProvider] = {}

    async def list_all(self) -> list[AIProvider]:
        return sorted(self._items.values(), key=lambda p: p.created_at)

    async def get(self, provider_id: UUID) -> AIProvider | None:
        return self._items.get(provider_id)

    async def create(self, provider: AIProvider) -> None:
        self._items[provider.id] = provider

    async def update(self, provider: AIProvider) -> None:
        old = self._items[provider.id]
        self._items[provider.id] = replace(provider, api_key=provider.api_key or old.api_key)

    async def delete(self, provider_id: UUID) -> bool:
        return self._items.pop(provider_id, None) is not None
