"""Подпись коммитов пользователя в Postgres: поля переживают запись и чтение."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.session import SessionProvider

from tests.contract.test_identity_contract import make_user

pytestmark = pytest.mark.pg


async def test__update__commit_identity__round_trips(pg_migrated_engine) -> None:  # type: ignore[no-untyped-def]
    users = SqlUserRepository(SessionProvider(create_sessionmaker(pg_migrated_engine)))
    await users.add(make_user("u1"))
    fresh = await users.get("u1")
    assert fresh is not None
    assert (fresh.commit_name, fresh.commit_email, fresh.commit_use_account_email) == (None, None, False)

    await users.update(
        replace(fresh, commit_name="A. I.", commit_email="a@home.example", commit_use_account_email=True)
    )

    stored = await users.get("u1")
    assert stored is not None
    assert (stored.commit_name, stored.commit_email, stored.commit_use_account_email) == (
        "A. I.",
        "a@home.example",
        True,
    )
