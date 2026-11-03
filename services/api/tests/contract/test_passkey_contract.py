"""Контракт репозитория passkey: одни и те же проверки на InMemory и Postgres, ключи двух людей не смешиваются."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.passkeys import IPasskeyRepository, Passkey, PasskeyVerificationError
from pytest_lazy_fixtures import lf

from tests.fakes.passkeys import InMemoryPasskeyRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

NOW = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)


def make_passkey(passkey_id: str, user_id: str = "ann", *, rp_id: str = "studio.test", minutes: int = 0) -> Passkey:
    return Passkey(
        id=passkey_id,
        user_id=user_id,
        credential_id=f"cred-{passkey_id}",
        public_key=b"\xa5\x01\x02" + passkey_id.encode(),
        sign_count=0,
        rp_id=rp_id,
        name=f"Ключ {passkey_id}",
        created_at=NOW + timedelta(minutes=minutes),
        transports=("internal", "hybrid"),
        aaguid="00000000-0000-0000-0000-000000000000",
        backup_eligible=True,
    )


@pytest_asyncio.fixture
async def memory_repo() -> IPasskeyRepository:
    return InMemoryPasskeyRepository()


@pytest_asyncio.fixture
async def pg_repo(pg_migrated_engine: AsyncEngine) -> IPasskeyRepository:
    from hse_doc_studio.infra.db.engine import create_sessionmaker
    from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
    from hse_doc_studio.infra.db.repositories.passkeys import SqlPasskeyRepository
    from hse_doc_studio.infra.db.session import SessionProvider

    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for user_id in ("ann", "bob"):
        email = f"{user_id}@example.test"
        await users.add(
            User(user_id, email, normalize_email(email), user_id.title(), UserStatus.active, created_at=NOW)
        )
    return SqlPasskeyRepository(sessions)


@pytest.fixture(params=[lf("memory_repo"), pytest.param(lf("pg_repo"), marks=pytest.mark.pg)], ids=["in_memory", "pg"])
def repo(request: pytest.FixtureRequest) -> IPasskeyRepository:
    return request.param


async def test__add__then_lookup_by_credential_and_user(repo: IPasskeyRepository) -> None:
    first, second = make_passkey("p1"), make_passkey("p2", minutes=5)
    await repo.add(second)
    await repo.add(first)

    assert await repo.get_by_credential_id("cred-p1") == first
    assert await repo.get_by_credential_id("cred-missing") is None
    assert await repo.list_for_user("ann") == [first, second]
    assert await repo.count_for_user("ann") == 2


async def test__add__duplicate_credential__rejected(repo: IPasskeyRepository) -> None:
    await repo.add(make_passkey("p1"))

    with pytest.raises(PasskeyVerificationError):
        await repo.add(replace(make_passkey("p1"), id="p9", user_id="bob"))

    assert await repo.count_for_user("bob") == 0


async def test__rename_and_delete__only_by_owner(repo: IPasskeyRepository) -> None:
    await repo.add(make_passkey("p1"))

    assert await repo.rename("bob", "p1", "чужой") is None
    assert not await repo.delete("bob", "p1")
    renamed = await repo.rename("ann", "p1", "Телефон")

    assert renamed is not None
    assert renamed.name == "Телефон"
    assert await repo.delete("ann", "p1")
    assert await repo.list_for_user("ann") == []


async def test__record_use__updates_counter_backup_and_time(repo: IPasskeyRepository) -> None:
    await repo.add(make_passkey("p1"))
    used_at = NOW + timedelta(hours=1)

    await repo.record_use("p1", sign_count=7, backed_up=True, now=used_at)

    stored = await repo.get_by_credential_id("cred-p1")
    assert stored is not None
    assert (stored.sign_count, stored.backed_up, stored.last_used_at) == (7, True, used_at)


async def test__two_people__keys_isolated_and_reset_per_person(repo: IPasskeyRepository) -> None:
    await repo.add(make_passkey("a1", "ann"))
    await repo.add(make_passkey("a2", "ann", rp_id="old.test"))
    await repo.add(make_passkey("b1", "bob"))

    assert [p.id for p in await repo.list_for_user("bob")] == ["b1"]
    assert await repo.count_by_rp_id() == {"studio.test": 2, "old.test": 1}
    assert await repo.delete_for_user("ann") == 2
    assert await repo.list_for_user("ann") == []
    assert [p.id for p in await repo.list_for_user("bob")] == ["b1"]
