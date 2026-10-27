from __future__ import annotations

import pytest
from hse_doc_studio.infra.db.leader import BACKGROUND_LEADER_LOCK_KEY, PgAdvisoryLeaderLock
from sqlalchemy import text

pytestmark = pytest.mark.pg


async def test__two_locks__only_one_leader_until_release(pg_engine) -> None:
    first, second = PgAdvisoryLeaderLock(pg_engine), PgAdvisoryLeaderLock(pg_engine)

    assert await first.acquire()
    assert not await second.acquire()
    assert await first.is_held()

    await first.release()

    assert not await first.is_held()
    assert await second.acquire()
    await second.release()


async def test__connection_lost__leadership_is_reported_lost(pg_engine) -> None:
    lock = PgAdvisoryLeaderLock(pg_engine)
    assert await lock.acquire()
    async with pg_engine.connect() as admin:
        await admin.execute(
            text("SELECT pg_terminate_backend(pid) FROM pg_locks WHERE locktype = 'advisory' AND objid = :key"),
            {"key": BACKGROUND_LEADER_LOCK_KEY},
        )

    assert not await lock.is_held()
    other = PgAdvisoryLeaderLock(pg_engine)
    assert await other.acquire()
    await other.release()
