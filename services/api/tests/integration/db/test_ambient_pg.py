from __future__ import annotations

import pytest
from hse_doc_studio.core.uow import spawn_detached
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

_INSERT = text("INSERT INTO instance_meta (key, value) VALUES (:k, 'v')")
_COUNT = text("SELECT count(*) FROM instance_meta")


async def _count(provider: SessionProvider) -> int:
    async with provider.use() as session:
        return (await session.execute(_COUNT)).scalar_one()


async def _write_then_fail(provider: SessionProvider) -> None:
    async with SqlUnitOfWork(provider).begin():
        async with provider.use() as session:
            await session.execute(_INSERT, {"k": "a"})
        async with provider.use() as session:
            await session.execute(_INSERT, {"k": "b"})
        raise RuntimeError("fail")


async def test__uow__exception__rolls_back_all_writes(pg_engine: AsyncEngine) -> None:
    await migrator.upgrade(pg_engine)
    provider = SessionProvider(create_sessionmaker(pg_engine))

    with pytest.raises(RuntimeError):
        await _write_then_fail(provider)

    assert await _count(provider) == 0


async def test__uow__success__commits_writes_of_several_calls(pg_engine: AsyncEngine) -> None:
    await migrator.upgrade(pg_engine)
    provider = SessionProvider(create_sessionmaker(pg_engine))

    async with SqlUnitOfWork(provider).begin():
        async with provider.use() as session:
            await session.execute(_INSERT, {"k": "a"})
        async with provider.use() as session:
            await session.execute(_INSERT, {"k": "b"})

    assert await _count(provider) == 2


async def test__detached_task__runs_beside_busy_transaction_on_own_connection(pg_engine: AsyncEngine) -> None:
    """Задача, отпущенная внутри транзакции, не делит её соединение: обе работают с БД одновременно."""
    await migrator.upgrade(pg_engine)
    provider = SessionProvider(create_sessionmaker(pg_engine))

    async def background() -> int:
        async with provider.use() as session:
            await session.execute(text("SELECT pg_sleep(0.05)"))
            return (await session.execute(_COUNT)).scalar_one()

    async with SqlUnitOfWork(provider).begin():
        async with provider.use() as session:
            await session.execute(_INSERT, {"k": "a"})
        task = spawn_detached(background())
        async with provider.use() as session:
            await session.execute(text("SELECT pg_sleep(0.2)"))
        # Незакоммиченную строку транзакции задача не видит: она в своей транзакции.
        assert await task == 0

    assert await _count(provider) == 1
