from __future__ import annotations

import pytest
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
