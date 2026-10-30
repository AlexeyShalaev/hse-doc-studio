"""Уборка хвостов задач против Postgres: выходы без владельца уходят, нужные остаются, старые строки стираются."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.jobs.retention import JobRetention
from hse_doc_studio.infra.storage.fs import FsObjectStore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

_PROJECT = uuid4()
# Объекты только что записаны, поэтому «сейчас» сдвигаем вперёд: они оказываются давними.
_LATER = datetime.now(tz=UTC) + timedelta(days=60)


class World:
    def __init__(self, engine: AsyncEngine, tmp_path: Path) -> None:
        self.engine = engine
        self.root = tmp_path / "jobs"
        self.store = FsObjectStore(tmp_path / "objects", max_object_bytes=10**6)
        self.sweep = JobRetention(
            SessionProvider(create_sessionmaker(engine)),
            self.store,
            self.root,
            output_min_age=timedelta(hours=24),
            retention=timedelta(days=30),
        )

    async def job(self, state: str, *, applied_days_ago: float | None = None) -> UUID:
        job_id = uuid4()
        applied = None if applied_days_ago is None else datetime.now(tz=UTC) - timedelta(days=applied_days_ago)
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO jobs (id, kind, state, project_id, user_id, tags, priority_class, vtime, queued_at, "
                    "max_attempts, timeout_s, payload, applied_at) "
                    "VALUES (:i, 'compile', :s, :p, :u, ARRAY[]::varchar[], 1, 0, now(), 1, 60, '{}'::jsonb, :a)"
                ),
                {"i": job_id, "s": state, "p": _PROJECT, "u": uuid4(), "a": applied},
            )
        return job_id

    async def output(self, job_id: UUID) -> str:
        key = f"artifacts/{_PROJECT}/jobs/{job_id}/main.pdf"
        await self.store.put(key, b"pdf")
        await self.store.put(f"announce/{_PROJECT}/{job_id}/1/{'a' * 64}.json", b"{}")
        return key

    async def alive(self, job_id: UUID) -> bool:
        return bool(await self.store.list_objects(f"artifacts/{_PROJECT}/jobs/{job_id}/"))

    async def rows(self) -> int:
        async with self.engine.connect() as conn:
            return int((await conn.execute(text("SELECT count(*) FROM jobs"))).scalar_one())


async def test__outputs__terminal_and_unknown_jobs_swept_live_ones_kept(
    pg_migrated_engine: AsyncEngine, tmp_path: Path
) -> None:
    w = World(pg_migrated_engine, tmp_path)
    cancelled = await w.job("cancelled")
    running = await w.job("running")
    unapplied_success = await w.job("succeeded")
    unknown = uuid4()
    for job_id in (cancelled, running, unapplied_success, unknown):
        await w.output(job_id)

    report = await w.sweep.run(_LATER)

    assert set(report.output_prefixes) == {cancelled, unknown}
    assert not await w.alive(cancelled)
    assert not await w.alive(unknown)
    assert await w.alive(running)
    assert await w.alive(unapplied_success)
    assert not await w.store.list_objects(f"announce/{_PROJECT}/{cancelled}/")


async def test__outputs__fresh_prefix_kept(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> None:
    w = World(pg_migrated_engine, tmp_path)
    job_id = await w.job("failed")
    await w.output(job_id)

    report = await w.sweep.run()

    assert report.output_prefixes == []
    assert await w.alive(job_id)


async def test__rows__old_applied_terminal_jobs_and_logs_removed(
    pg_migrated_engine: AsyncEngine, tmp_path: Path
) -> None:
    w = World(pg_migrated_engine, tmp_path)
    old = await w.job("succeeded", applied_days_ago=40)
    recent = await w.job("failed", applied_days_ago=1)
    pending = await w.job("failed")
    log = w.root / "logs" / str(old)
    log.mkdir(parents=True)
    (log / "1.log").write_text("x")

    report = await w.sweep.run()

    assert report.rows == 1
    assert await w.rows() == 2
    assert not log.exists()
    del recent, pending
