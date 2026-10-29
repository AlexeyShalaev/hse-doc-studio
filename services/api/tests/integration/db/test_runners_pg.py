"""Postgres-репозитории раннеров: списание токена регистрации под гонкой, bootstrap, уникальность хеша."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.jobs.runners import RegistrationToken, Runner
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.runners import SqlRegistrationTokenRepository, SqlRunnerRepository
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def _repos(engine: AsyncEngine) -> tuple[SqlRunnerRepository, SqlRegistrationTokenRepository]:
    sessions = SessionProvider(create_sessionmaker(engine))
    return SqlRunnerRepository(sessions), SqlRegistrationTokenRepository(sessions)


def _token(token_id: str, token_hash: str, **kwargs: object) -> RegistrationToken:
    return RegistrationToken(
        id=token_id,
        token_hash=token_hash,
        created_by="admin",
        created_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        **kwargs,  # type: ignore[arg-type]
    )


def _runner(runner_id: str, token_hash: str) -> Runner:
    return Runner(
        id=runner_id,
        name="r",
        token_hash=token_hash,
        tags=frozenset({"office", "verify"}),
        concurrency=2,
        resource_class="standard",
        version="0.3.0",
        created_at=NOW,
    )


async def test__consume__concurrent_claimers__single_use_token_spent_once(pg_migrated_engine: AsyncEngine) -> None:
    _, tokens = _repos(pg_migrated_engine)
    await tokens.add(_token("t1", "h1"))

    results = await asyncio.gather(*(tokens.consume("h1", NOW) for _ in range(12)))

    assert sum(r is not None for r in results) == 1
    assert (await tokens.get("t1")).uses == 1  # type: ignore[union-attr]


async def test__consume__rejects_expired_revoked_and_unknown(pg_migrated_engine: AsyncEngine) -> None:
    _, tokens = _repos(pg_migrated_engine)
    await tokens.add(_token("t1", "h1", max_uses=3))
    await tokens.add(_token("t2", "h2"))

    assert await tokens.consume("h1", NOW + timedelta(hours=2)) is None
    assert await tokens.revoke("t2", NOW) is True
    assert await tokens.revoke("t2", NOW) is False
    assert await tokens.consume("h2", NOW) is None
    assert await tokens.consume("nope", NOW) is None
    assert (await tokens.consume("h1", NOW)).uses == 1  # type: ignore[union-attr]


async def test__upsert_bootstrap__same_secret_keeps_counter_new_secret_resets(pg_migrated_engine: AsyncEngine) -> None:
    _, tokens = _repos(pg_migrated_engine)
    boot = RegistrationToken(id="bootstrap", token_hash="b1", created_by=None, created_at=NOW, expires_at=None)

    await tokens.upsert_bootstrap(boot)
    assert await tokens.consume("b1", NOW) is not None
    await tokens.upsert_bootstrap(boot)
    assert await tokens.consume("b1", NOW) is None

    await tokens.upsert_bootstrap(RegistrationToken(**{**boot.__dict__, "token_hash": "b2"}))
    assert await tokens.consume("b1", NOW) is None
    assert await tokens.consume("b2", NOW) is not None


async def test__runners__roundtrip_rotate_pause_revoke(pg_migrated_engine: AsyncEngine) -> None:
    runners, _ = _repos(pg_migrated_engine)
    await runners.add(_runner("r1", "h1"))

    stored = await runners.get_by_token_hash("h1")
    assert stored is not None
    assert stored.tags == frozenset({"office", "verify"})
    assert await runners.set_token_hash("r1", "h2") is True
    assert await runners.get_by_token_hash("h1") is None
    assert await runners.set_paused("r1", True) is True
    await runners.touch("r1", NOW + timedelta(seconds=5), "0.3.1")
    assert await runners.revoke("r1", NOW) is True
    assert await runners.set_token_hash("r1", "h3") is False
    final = (await runners.list())[0]
    assert (final.paused, final.version, final.revoked_at, final.last_seen_at) == (
        True,
        "0.3.1",
        NOW,
        NOW + timedelta(seconds=5),
    )
    assert await runners.revoke("missing", NOW) is False


async def test__runners__duplicate_token_hash__rejected(pg_migrated_engine: AsyncEngine) -> None:
    runners, _ = _repos(pg_migrated_engine)
    await runners.add(_runner("r1", "same"))

    with pytest.raises(IntegrityError):
        await runners.add(_runner("r2", "same"))
