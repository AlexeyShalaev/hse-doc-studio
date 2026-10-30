"""Планы запросов списков админки эксплуатации: на тысячах строк фильтр и порядок идут по индексу.

Запрос берётся ровно тот, что строит читатель (перехват перед отправкой), и разбирается EXPLAIN после ANALYZE.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from hse_doc_studio.core.jobs.admin import JobAdminFilter, RegistrationTokenQuery
from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.quotas import org_key
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.jobs import JobRow, RunnerRegistrationTokenRow
from hse_doc_studio.infra.db.repositories.jobs_admin import SqlJobAdminReader
from hse_doc_studio.infra.db.repositories.runners import SqlRunnerAdminReader
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy import event, insert, text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
JOBS = 20_000
USERS = 400
RUNNERS = 400
PROJECTS = 2_000
TOKENS = 3_000
ORG = "org_" + "a" * 32


def _states(i: int) -> str:
    # Почти всё завершено; выполняющихся мало, как на живой установке.
    return "running" if i % 400 == 0 else ("succeeded", "failed")[i % 2]


async def _seed(engine: AsyncEngine) -> None:
    rows = [
        {
            "id": UUID(int=1_000_000 + i),
            "kind": "compile",
            "state": _states(i),
            "project_id": UUID(int=i % PROJECTS + 1),
            "user_id": UUID(int=i % USERS + 1),
            "org_id": org_key(ORG) if i % 200 == 0 else None,
            "tags": ["tex"],
            "priority_class": 1,
            "vtime": 0.0,
            "queued_at": NOW - timedelta(seconds=JOBS - i),
            "max_attempts": 3,
            "timeout_s": 600.0,
            "payload": {},
            "runner_id": UUID(int=i % RUNNERS + 1),
        }
        for i in range(JOBS)
    ]
    tokens = [
        {
            "id": f"rt_{i:05d}",
            "token_hash": f"{i:064d}",
            "label": f"token {i}",
            "max_uses": 1,
            "uses": 0,
            "created_at": NOW - timedelta(minutes=i),
            "expires_at": NOW + timedelta(days=1),
        }
        for i in range(TOKENS)
    ]
    async with engine.begin() as conn:
        await conn.execute(insert(JobRow), rows)
        await conn.execute(insert(RunnerRegistrationTokenRow), tokens)
    async with engine.connect() as conn:
        await conn.execute(text("ANALYZE jobs"))
        await conn.execute(text("ANALYZE runner_registration_tokens"))
        await conn.commit()


class _Captured:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def __call__(self, _conn: Any, _cursor: Any, statement: str, parameters: Any, *_args: Any) -> None:
        self.calls.append((statement, parameters))


def _capturing(engine: AsyncEngine) -> Iterator[_Captured]:
    captured = _Captured()
    event.listen(engine.sync_engine, "before_cursor_execute", captured)
    try:
        yield captured
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", captured)


async def _plan(engine: AsyncEngine, run: Callable[[], Awaitable[object]], marker: str) -> dict[str, Any]:
    """План первого запроса, в тексте которого есть `marker` (основной SELECT страницы)."""
    gen = _capturing(engine)
    captured = next(gen)
    try:
        await run()
    finally:
        gen.close()
    statement, parameters = next((s, p) for s, p in captured.calls if marker in s and "count(" not in s)
    async with engine.connect() as conn:
        raw = (await conn.exec_driver_sql(f"EXPLAIN (FORMAT JSON) {statement}", parameters)).scalar_one()
    return (json.loads(raw) if isinstance(raw, str) else raw)[0]["Plan"]


def _nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", ()):
        yield from _nodes(child)


def _indexes(plan: dict[str, Any]) -> set[str]:
    return {n["Index Name"] for n in _nodes(plan) if "Index Name" in n}


def _scans_jobs(plan: dict[str, Any]) -> bool:
    """Читается ли jobs целиком: на больших таблицах страница должна идти по индексу."""
    return any(n["Node Type"] == "Seq Scan" and n.get("Relation Name") == "jobs" for n in _nodes(plan))


@pytest.fixture
async def seeded(pg_migrated_engine: AsyncEngine) -> AsyncEngine:
    await _seed(pg_migrated_engine)
    return pg_migrated_engine


@pytest.mark.parametrize(
    ("flt", "index"),
    [
        (JobAdminFilter(user_id=UUID(int=7)), "ix_jobs_user_id_seq"),
        (JobAdminFilter(runner_id=UUID(int=3)), "ix_jobs_runner_id_seq"),
        (JobAdminFilter(org_id=org_key(ORG)), "ix_jobs_org_id_seq"),
        (JobAdminFilter(project_id=UUID(int=11)), "ix_jobs_project_id_seq"),
    ],
    ids=["user", "runner", "org", "project"],
)
async def test__queue_page__filter_uses_composite_index(seeded: AsyncEngine, flt: JobAdminFilter, index: str) -> None:
    reader = SqlJobAdminReader(SessionProvider(create_sessionmaker(seeded)))

    plan = await _plan(seeded, lambda: reader.list_jobs(flt, before_seq=None, limit=50), "FROM jobs")

    assert index in _indexes(plan), json.dumps(plan)[:2000]
    assert not _scans_jobs(plan)


async def test__queue_page__state_filter_reads_an_index_not_the_table(seeded: AsyncEngine) -> None:
    """Для редкого состояния годятся и частичные индексы очереди: важно, что jobs не читается целиком."""
    reader = SqlJobAdminReader(SessionProvider(create_sessionmaker(seeded)))
    flt = JobAdminFilter(states=frozenset({JobState.running}))

    plan = await _plan(seeded, lambda: reader.list_jobs(flt, before_seq=None, limit=50), "FROM jobs")

    assert _indexes(plan), json.dumps(plan)[:2000]
    assert not _scans_jobs(plan)


async def test__queue_page__unfiltered_and_next_page_read_seq_index_backwards(seeded: AsyncEngine) -> None:
    reader = SqlJobAdminReader(SessionProvider(create_sessionmaker(seeded)))

    first = await _plan(seeded, lambda: reader.list_jobs(JobAdminFilter(), before_seq=None, limit=50), "FROM jobs")
    deep = await _plan(seeded, lambda: reader.list_jobs(JobAdminFilter(), before_seq=500, limit=50), "FROM jobs")

    for plan in (first, deep):
        assert not _scans_jobs(plan), json.dumps(plan)[:2000]
        assert any(name.startswith("jobs_seq") or name.endswith("_seq") for name in _indexes(plan))


async def test__queue_page__estimate_without_filters_comes_from_statistics(seeded: AsyncEngine) -> None:
    reader = SqlJobAdminReader(SessionProvider(create_sessionmaker(seeded)))

    plain = await reader.list_jobs(JobAdminFilter(), before_seq=None, limit=1)
    filtered = await reader.list_jobs(JobAdminFilter(user_id=UUID(int=7)), before_seq=None, limit=1)

    assert plain.total_estimate is not None
    assert abs(plain.total_estimate - JOBS) <= JOBS // 10
    assert filtered.total_estimate is None


async def test__registration_tokens__newest_first_reads_created_at_index(seeded: AsyncEngine) -> None:
    reader = SqlRunnerAdminReader(SessionProvider(create_sessionmaker(seeded)))

    plan = await _plan(
        seeded, lambda: reader.list_tokens(RegistrationTokenQuery(), NOW), "FROM runner_registration_tokens"
    )

    assert "ix_runner_registration_tokens_created_at" in _indexes(plan), json.dumps(plan)[:2000]
