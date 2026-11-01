"""Блокирующее чтение пользователя: запись по устаревшему снимку не затирает чужую правку."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from hse_doc_studio.core.identity.entities import UserStatus
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.session import SessionProvider

from tests.contract.test_identity_contract import make_user

pytestmark = pytest.mark.pg


async def test__get_for_update__second_reader_waits_and_sees_committed_change(pg_migrated_engine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    user = make_user("u1")
    await users.add(user)
    locked = asyncio.Event()

    async def admin_disables() -> None:
        async with sessions.begin():
            current = await users.get_for_update(user.id)
            assert current is not None
            locked.set()
            await asyncio.sleep(0.3)
            await users.update(replace(current, status=UserStatus.disabled))

    async def login_reads() -> UserStatus:
        await locked.wait()
        async with sessions.begin():
            current = await users.get_for_update(user.id)
            assert current is not None
            return current.status

    _, status = await asyncio.gather(admin_disables(), login_reads())

    assert status is UserStatus.disabled
