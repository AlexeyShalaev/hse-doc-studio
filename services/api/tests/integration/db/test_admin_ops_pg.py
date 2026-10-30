"""Postgres-читатели админки: страницы очереди с фильтрами, сводка очереди, место по базе."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.admin import JobAdminFilter
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass, JobState
from hse_doc_studio.core.jobs.queue import EnqueueRequest, RunnerRef
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.blobs import BlobRow
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.repositories.jobs_admin import SqlJobAdminReader
from hse_doc_studio.infra.db.repositories.storage_usage import SqlStorageUsageReader
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def _request(user: UUID, **kwargs: object) -> EnqueueRequest:
    return EnqueueRequest(
        job_id=uuid4(),
        kind=JobKind.compile,
        project_id=uuid4(),
        user_id=user,
        tags=frozenset({"tex"}),
        payload={"n": 1},
        **kwargs,  # type: ignore[arg-type]
    )


async def test__list_jobs__filters_and_keyset_pages_newest_first(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    queue = PostgresJobQueue(sessions)
    reader = SqlJobAdminReader(sessions)
    anna, boris = uuid4(), uuid4()
    for user in (anna, boris, anna, anna):
        await queue.enqueue(_request(user))
    await queue.enqueue(_request(boris, priority_class=JobPriorityClass.batch))

    only_anna = await reader.list_jobs(JobAdminFilter(user_id=anna), before_seq=None, limit=2)
    rest = await reader.list_jobs(JobAdminFilter(user_id=anna), before_seq=only_anna.next_before_seq, limit=2)
    everything = await reader.list_jobs(JobAdminFilter(), before_seq=None, limit=50)
    running = await reader.list_jobs(JobAdminFilter(states=frozenset({JobState.running})), before_seq=None, limit=50)

    assert [j.job.user_id for j in only_anna.items] == [anna, anna]
    assert only_anna.next_before_seq is not None
    assert len(rest.items) == 1
    assert rest.next_before_seq is None
    seqs = [j.job.seq for j in everything.items]
    assert seqs == sorted(seqs, reverse=True)
    assert len(everything.items) == 5
    assert running.items == ()


async def test__stats__counts_states_classes_oldest_and_waits(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    queue = PostgresJobQueue(sessions)
    reader = SqlJobAdminReader(sessions)
    empty = await reader.stats(datetime.now(UTC))
    assert (empty.by_state, empty.oldest_queued_at, empty.wait_p50_s) == ({}, None, None)

    for _ in range(3):
        await queue.enqueue(_request(uuid4()))
    await queue.enqueue(_request(uuid4(), priority_class=JobPriorityClass.batch))
    taken = await queue.claim(RunnerRef(id=uuid4(), tags=frozenset({"tex"})), lease_s=45)
    assert taken is not None

    stats = await reader.stats(datetime.now(UTC))

    assert stats.by_state == {JobState.queued: 3, JobState.running: 1}
    assert sum(stats.queued_by_class.values()) == 3
    assert stats.oldest_queued_at is not None
    assert stats.wait_p50_s is not None
    assert stats.wait_p50_s >= 0
    assert stats.wait_p95_s is not None
    assert stats.wait_p95_s >= stats.wait_p50_s


async def test__storage_usage__counts_blobs_projects_and_owners_from_db(
    pg_migrated_engine: AsyncEngine, tmp_path: Path
) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    async with sessions.use() as session:
        for uid, name in (("u1", "Анна"), ("u2", "Boris")):
            session.add(
                UserRow(
                    id=uid,
                    email=f"{uid}@example.org",
                    email_normalized=f"{uid}@example.org",
                    name=name,
                    status="active",
                    created_at=NOW,
                )
            )
        await session.flush()
        for n, (owner, deleted) in enumerate((("u1", None), ("u1", None), ("u2", None), ("u2", NOW))):
            session.add(
                ProjectRow(
                    id=uuid4(),
                    name=f"p{n}",
                    owner_user_id=owner,
                    workspace_path=f"/w/{n}",
                    kind="solo",
                    lang="ru",
                    deleted_at=deleted,
                )
            )
        session.add_all([BlobRow(sha256="a" * 64, size=100), BlobRow(sha256="b" * 64, size=250)])

    usage = await SqlStorageUsageReader(sessions, tmp_path).read(NOW + timedelta(seconds=1))

    assert (usage.blob_count, usage.blob_bytes) == (2, 350)
    assert (usage.projects, usage.deleted_projects) == (3, 1)
    assert [(o.owner_id, o.projects) for o in usage.top_owners] == [("u1", 2), ("u2", 1)]
    assert usage.volume_total_bytes is not None
    assert usage.volume_free_bytes is not None
    assert usage.computed_at == NOW + timedelta(seconds=1)


async def test__storage_usage__no_volume__none(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))

    usage = await SqlStorageUsageReader(sessions, None).read(NOW)

    assert (usage.blob_count, usage.blob_bytes, usage.projects) == (0, 0, 0)
    assert (usage.volume_total_bytes, usage.volume_free_bytes) == (None, None)
