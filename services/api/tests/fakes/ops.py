"""Фейки админки эксплуатации: читатель очереди поверх InMemoryJobQueue, счётчик места, шифр и транзакция."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderOwnerKind
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.jobs.admin import JobAdminFilter, JobAdminPage, JobListing, QueueStats
from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.queue import QueuedJob
from hse_doc_studio.core.listing import Found, Picked, PickerItem
from hse_doc_studio.core.repositories import InstanceAiProviderQuery
from hse_doc_studio.core.storage.usage import StorageOwner, StorageOwnerQuery, StorageUsage

from tests.fakes.job_queue import InMemoryJobQueue


def _matches(job: QueuedJob, flt: JobAdminFilter) -> bool:
    return (
        (not flt.states or job.state in flt.states)
        and (not flt.kinds or job.kind in flt.kinds)
        and (flt.user_id is None or job.user_id == flt.user_id)
        and (flt.org_id is None or job.org_id == flt.org_id)
        and (flt.project_id is None or job.project_id == flt.project_id)
        and (flt.runner_id is None or job.runner_id == flt.runner_id)
        and (flt.queued_from is None or job.queued_at >= flt.queued_from)
        and (flt.queued_to is None or job.queued_at < flt.queued_to)
    )


class InMemoryJobAdminReader:
    """Читатель очереди без подписей: имён людей и проектов фейк не знает, кроме заданных в `names`."""

    def __init__(self, queue: InMemoryJobQueue, names: dict[UUID, str] | None = None) -> None:
        self._queue = queue
        self._names = names or {}

    def _listing(self, job: QueuedJob) -> JobListing:
        return JobListing(job=job, user_name=self._names.get(job.user_id))

    async def list_jobs(self, flt: JobAdminFilter, *, before_seq: int | None, limit: int) -> JobAdminPage:
        jobs = [
            j
            for j in reversed(await self._queue.list())
            if _matches(j, flt) and (before_seq is None or j.seq < before_seq)
        ]
        page = jobs[:limit]
        return JobAdminPage(
            items=tuple(self._listing(j) for j in page),
            next_before_seq=page[-1].seq if len(jobs) > limit and page else None,
            total_estimate=len(await self._queue.list()) if flt.empty else None,
        )

    async def get(self, job_id: UUID) -> JobListing | None:
        found = await self._queue.get(job_id)
        return None if found is None else self._listing(found)

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


class FixedProjectPicker:
    def __init__(self, names: dict[str, str] | None = None) -> None:
        self._names = names or {}

    async def pick(self, q: str | None, limit: int) -> Picked[PickerItem]:
        found = sorted((n, i) for i, n in self._names.items() if (q or "").lower() in n.lower())
        items = [PickerItem(kind="project", id=i, name=n) for n, i in found[:limit]]
        return Picked(items=items, has_more=len(found) > limit)


class CountingStorageReader:
    def __init__(self, owners: list[StorageOwner] | None = None) -> None:
        self.reads = 0
        self.owners = owners or []

    async def list_owners(self, query: StorageOwnerQuery) -> Found[StorageOwner]:
        found = [o for o in self.owners if not query.kinds or o.kind in query.kinds]
        w = query.window
        return Found(items=list(found[w.offset : w.offset + w.limit]), total=len(found))

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


class FixedServerKeyCounter:
    def __init__(self, count: int = 0) -> None:
        self.count = count

    async def count_server_keys(self) -> int:
        return self.count


class InMemoryAIProviderRepository:
    """IAIProviderRepository без шифрования: как у сервера, пустой ключ при обновлении оставляет прежний."""

    def __init__(self) -> None:
        self._items: dict[UUID, AIProvider] = {}

    async def list_all(self) -> list[AIProvider]:
        return sorted(self._items.values(), key=lambda p: p.created_at)

    async def list_instance(self, query: InstanceAiProviderQuery) -> Found[AIProvider]:
        needle = (query.q or "").lower()
        found = [
            p
            for p in await self.list_all()
            if p.owner_kind is AIProviderOwnerKind.instance
            and (not needle or needle in f"{p.name} {p.base_url}".lower())
            and (not query.types or p.type in query.types)
        ]
        w = query.window
        return Found(items=list(found[w.offset : w.offset + w.limit]), total=len(found))

    async def get(self, provider_id: UUID) -> AIProvider | None:
        return self._items.get(provider_id)

    async def create(self, provider: AIProvider) -> None:
        self._items[provider.id] = provider

    async def update(self, provider: AIProvider) -> None:
        old = self._items[provider.id]
        self._items[provider.id] = replace(provider, api_key=provider.api_key or old.api_key)

    async def delete(self, provider_id: UUID) -> bool:
        return self._items.pop(provider_id, None) is not None
