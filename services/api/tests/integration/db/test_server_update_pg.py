"""Запуски автообновления в Postgres: один активный запуск, захват очереди, события, версии, которые не возвращаем."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.listing import Window
from hse_doc_studio.core.server_update.entities import RunEvent, RunKind, RunStatus, RunTrigger, UpdateRun
from hse_doc_studio.core.server_update.protocols import append_events
from hse_doc_studio.infra.db import orm  # noqa: F401
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.server_update import SqlUpdateRunRepository
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

NOW = datetime(2026, 11, 3, 2, tzinfo=UTC)


def _run(
    status: RunStatus = RunStatus.queued,
    *,
    kind: RunKind = RunKind.update,
    to: str = "0.4.0",
    frm: str = "0.3.1",
    minutes: int = 0,
) -> UpdateRun:
    return UpdateRun(
        id=str(uuid4()),
        kind=kind,
        trigger=RunTrigger.auto,
        status=status,
        from_version=frm,
        to_version=to,
        created_at=NOW + timedelta(minutes=minutes),
        events=(RunEvent(0, NOW, "request", "info", "requested"),),
    )


@pytest.fixture
def sessions(pg_migrated_engine: AsyncEngine) -> SessionProvider:
    return SessionProvider(create_sessionmaker(pg_migrated_engine))


async def test__only_one_active_run_and_finishing_releases_the_slot(sessions: SessionProvider) -> None:
    runs = SqlUpdateRunRepository(sessions)
    first, second = _run(), _run()
    assert await runs.add(first)
    assert not await runs.add(second)
    active = await runs.active()
    assert active is not None
    assert active.id == first.id
    await runs.save(first.with_(status=RunStatus.succeeded, finished_at=NOW))
    assert await runs.active() is None
    assert await runs.add(second)


async def test__claim_next_takes_the_oldest_queued_run_once(sessions: SessionProvider) -> None:
    runs = SqlUpdateRunRepository(sessions)
    waiting = _run(RunStatus.waiting_backup)
    await runs.add(waiting)
    assert await runs.claim_next(now_iso=NOW.isoformat()) is None, "ждущий бэкап запуск апдейтеру не отдаётся"
    await runs.save(waiting.with_(status=RunStatus.queued))
    claimed = await runs.claim_next(now_iso=NOW.isoformat())
    assert claimed is not None
    assert (claimed.id, claimed.status, claimed.phase) == (waiting.id, RunStatus.running, "preflight")
    assert claimed.started_at == NOW
    assert await runs.claim_next(now_iso=NOW.isoformat()) is None


async def test__events_roundtrip_in_order_with_revisions(sessions: SessionProvider) -> None:
    runs = SqlUpdateRunRepository(sessions)
    run = _run(RunStatus.running)
    await runs.add(run)
    loaded = await runs.lock(run.id)
    assert loaded is not None
    updated = append_events(
        loaded.with_(from_revision="r1", to_revision="r2", db_restored=True),
        [RunEvent(1, NOW, "snapshot", "info", "снимок"), RunEvent(2, NOW, "finish", "warn", "итог")],
    )
    await runs.save(updated)
    again = await runs.get(run.id)
    assert again is not None
    assert [e.seq for e in again.events] == [0, 1, 2]
    assert again.events[1].message == "снимок"
    assert (again.from_revision, again.to_revision, again.db_restored, again.last_seq) == ("r1", "r2", True, 2)


async def test__failed_targets_and_history(sessions: SessionProvider) -> None:
    runs = SqlUpdateRunRepository(sessions)
    await runs.add(_run(RunStatus.rolled_back, to="0.4.0", minutes=0))
    await runs.add(_run(RunStatus.failed, to="0.5.0", minutes=1))
    await runs.add(_run(RunStatus.succeeded, to="0.3.5", minutes=2))
    await runs.add(_run(RunStatus.succeeded, kind=RunKind.rollback, frm="0.3.5", to="0.3.1", minutes=3))
    assert await runs.failed_targets() == {"0.4.0", "0.5.0", "0.3.5"}
    page = await runs.page(Window(limit=2, offset=0))
    assert page.total == 4
    assert [r.kind for r in page.items] == [RunKind.rollback, RunKind.update]
    ok = await runs.last_succeeded_update()
    assert ok is not None
    assert ok.to_version == "0.3.5"
    last = await runs.last_finished()
    assert last is not None
    assert last.kind is RunKind.rollback
    counts = await runs.counts()
    assert counts[RunStatus.succeeded] == 2


async def test__downgrade_kind_is_stored_and_revisions_are_learned_from_history(sessions: SessionProvider) -> None:
    runs = SqlUpdateRunRepository(sessions)
    first = _run(RunStatus.succeeded, to="0.3.2", frm="0.3.1", minutes=0).with_(from_revision="r1", to_revision="r2")
    down = _run(RunStatus.succeeded, kind=RunKind.downgrade, to="0.3.1", frm="0.3.2", minutes=1).with_(
        from_revision="r2", to_revision="r2"
    )
    stray = _run(RunStatus.rolled_back, to="0.9.0", frm="0.3.1", minutes=2).with_(from_revision="r2", to_revision="r9")
    for run in (first, down, stray):
        assert await runs.add(run)

    got = await runs.get(down.id)
    assert got is not None
    assert got.kind is RunKind.downgrade
    assert await runs.known_revisions() == {"0.3.1": "r2", "0.3.2": "r2"}
    # откат на выбранную версию, как и ручной, помечает версию, с которой ушли: автоустановка её не вернёт
    assert "0.3.2" in await runs.failed_targets()
