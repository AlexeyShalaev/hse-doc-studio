"""Контракт репозиториев identity: одни и те же проверки на InMemory и Postgres."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from hse_doc_studio.core.identity.entities import User, UserIdentity, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.protocols import (
    ICredentialRepository,
    IFirstAdminRepository,
    IInstanceSettingsRepository,
    IUserRepository,
)
from pytest_lazy_fixtures import lf

from tests.fakes.identity import (
    InMemoryCredentialRepository,
    InMemoryFirstAdminRepository,
    InMemoryIdentityStore,
    InMemoryInstanceSettingsRepository,
    InMemoryUserRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)


@dataclass
class Repos:
    users: IUserRepository
    credentials: ICredentialRepository
    first_admin: IFirstAdminRepository
    settings: IInstanceSettingsRepository


def make_user(user_id: str, email: str = "", *, admin: bool = False) -> User:
    email = email or f"{user_id}@example.test"
    return User(
        id=user_id,
        email=email,
        email_normalized=normalize_email(email),
        name=user_id.title(),
        status=UserStatus.active,
        created_at=NOW,
        is_instance_admin=admin,
    )


@pytest_asyncio.fixture
async def memory_repos() -> Repos:
    store = InMemoryIdentityStore()
    return Repos(
        InMemoryUserRepository(store),
        InMemoryCredentialRepository(store),
        InMemoryFirstAdminRepository(store),
        InMemoryInstanceSettingsRepository(),
    )


@pytest_asyncio.fixture
async def pg_repos(pg_migrated_engine: AsyncEngine) -> Repos:
    from hse_doc_studio.infra.db.engine import create_sessionmaker
    from hse_doc_studio.infra.db.repositories.identity import (
        SqlCredentialRepository,
        SqlFirstAdminRepository,
        SqlInstanceSettingsRepository,
        SqlUserRepository,
    )
    from hse_doc_studio.infra.db.session import SessionProvider

    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    return Repos(
        SqlUserRepository(sessions),
        SqlCredentialRepository(sessions),
        SqlFirstAdminRepository(sessions),
        SqlInstanceSettingsRepository(sessions),
    )


@pytest.fixture(
    params=[lf("memory_repos"), pytest.param(lf("pg_repos"), marks=pytest.mark.pg)], ids=["in_memory", "pg"]
)
def repos(request: pytest.FixtureRequest) -> Repos:
    return request.param


async def test__add__then_get__returns_user(repos: Repos) -> None:
    user = make_user("u1", "Ann@Example.Test")
    await repos.users.add(user)
    assert await repos.users.get("u1") == user
    assert await repos.users.get("missing") is None
    assert await repos.users.count() == 1


async def test__get_by_email__ignores_case_and_spaces(repos: Repos) -> None:
    user = make_user("u1", "Ann@Example.Test")
    await repos.users.add(user)
    found = await repos.users.get_by_email("  ANN@example.TEST ")
    assert found is not None
    assert found.id == "u1"
    assert await repos.users.get_by_email("other@example.test") is None


async def test__add__duplicate_email_other_case__raises_email_taken(repos: Repos) -> None:
    await repos.users.add(make_user("u1", "ann@example.test"))
    with pytest.raises(IdentityError) as err:
        await repos.users.add(make_user("u2", "ANN@example.test"))
    assert err.value.code is IdentityErrorCode.email_taken
    assert await repos.users.count() == 1


async def test__update__changes_fields(repos: Repos) -> None:
    user = make_user("u1")
    await repos.users.add(user)
    changed = replace(user, name="New", status=UserStatus.disabled, locale="en", last_login_at=NOW, email_verified=True)
    await repos.users.update(changed)
    assert await repos.users.get("u1") == changed


async def test__update__email_of_other_user__raises_email_taken(repos: Repos) -> None:
    await repos.users.add(make_user("u1", "a@example.test"))
    second = make_user("u2", "b@example.test")
    await repos.users.add(second)
    with pytest.raises(IdentityError) as err:
        await repos.users.update(replace(second, email="A@example.test", email_normalized="a@example.test"))
    assert err.value.code is IdentityErrorCode.email_taken


async def test__lock_active_admins__counts_only_active_admins(repos: Repos) -> None:
    await repos.users.add(make_user("a", admin=True))
    await repos.users.add(make_user("b", admin=True))
    await repos.users.add(make_user("m"))
    await repos.users.add(replace(make_user("d", admin=True), status=UserStatus.disabled))

    assert await repos.users.lock_active_admins() == 2


async def test__identity__add_then_lookup__returns_user(repos: Repos) -> None:
    await repos.users.add(make_user("u1"))
    identity = UserIdentity(user_id="u1", provider="corp", subject="sub-1", email="x@corp.test", email_verified=True)
    await repos.users.add_identity(identity)
    found = await repos.users.get_by_identity("corp", "sub-1")
    assert found is not None
    assert found.id == "u1"
    assert await repos.users.get_by_identity("corp", "other") is None
    assert await repos.users.list_identities("u1") == [identity]
    assert await repos.users.list_identities("u2") == []


async def test__identity__same_pair_twice__rejected(repos: Repos) -> None:
    await repos.users.add(make_user("u1"))
    await repos.users.add(make_user("u2"))
    await repos.users.add_identity(UserIdentity(user_id="u1", provider="corp", subject="s"))
    with pytest.raises(IdentityError):
        await repos.users.add_identity(UserIdentity(user_id="u2", provider="corp", subject="s"))


async def test__credentials__set_replaces_hash(repos: Repos) -> None:
    await repos.users.add(make_user("u1"))
    assert await repos.credentials.get_hash("u1") is None
    await repos.credentials.set_hash("u1", "h1")
    await repos.credentials.set_hash("u1", "h2")
    assert await repos.credentials.get_hash("u1") == "h2"


async def test__create_first_admin__stores_user_and_hash(repos: Repos) -> None:
    await repos.first_admin.create_first_admin(make_user("a1", admin=True), "hash")
    found = await repos.users.get("a1")
    assert found is not None
    assert found.is_instance_admin
    assert await repos.credentials.get_hash("a1") == "hash"


async def test__create_first_admin__admin_exists__raises_setup_already_done(repos: Repos) -> None:
    await repos.first_admin.create_first_admin(make_user("a1", admin=True), "hash")
    with pytest.raises(IdentityError) as err:
        await repos.first_admin.create_first_admin(make_user("a2", admin=True), "hash2")
    assert err.value.code is IdentityErrorCode.setup_already_done
    assert await repos.users.count() == 1


async def test__create_first_admin__email_taken__leaves_no_admin(repos: Repos) -> None:
    await repos.users.add(make_user("u1", "a@example.test"))
    with pytest.raises(IdentityError) as err:
        await repos.first_admin.create_first_admin(make_user("a1", "A@example.test", admin=True), "hash")
    assert err.value.code is IdentityErrorCode.email_taken
    assert await repos.credentials.get_hash("a1") is None


async def test__create_first_admin__parallel__only_one_wins(repos: Repos) -> None:
    candidates = [make_user(f"a{i}", admin=True) for i in range(5)]
    results = await asyncio.gather(
        *(repos.first_admin.create_first_admin(u, f"h{u.id}") for u in candidates), return_exceptions=True
    )
    failures = [r for r in results if isinstance(r, IdentityError)]
    assert len(failures) == 4
    assert all(f.code is IdentityErrorCode.setup_already_done for f in failures)
    assert sum(1 for r in results if r is None) == 1
    assert await repos.users.count() == 1


async def test__instance_settings__set_get_overwrite(repos: Repos) -> None:
    assert dict(await repos.settings.get_all()) == {}
    await repos.settings.set("auth", {"registration_mode": "invite", "domains": ["a.test"]}, source="setup")
    await repos.settings.set("flag", True, source="setup")
    await repos.settings.set("flag", False, source="admin")
    assert dict(await repos.settings.get_all()) == {
        "auth": {"registration_mode": "invite", "domains": ["a.test"]},
        "flag": False,
    }


async def test__settings__delete_returns_to_default_and_ignores_missing_key(repos: Repos) -> None:
    await repos.settings.set("smtp.host", "smtp.example.org", source="admin")

    await repos.settings.delete("smtp.host")
    await repos.settings.delete("smtp.host")

    assert "smtp.host" not in await repos.settings.get_all()


async def test__settings__secret_is_stored_apart_and_visible_only_as_a_marker(repos: Repos) -> None:
    assert await repos.settings.get_secret("smtp.password") is None

    await repos.settings.set_secret("smtp.password", "token-1", source="admin")
    await repos.settings.set_secret("smtp.password", "token-2", source="admin")

    assert await repos.settings.get_secret("smtp.password") == "token-2"
    assert (await repos.settings.get_all())["smtp.password"] is True
    await repos.settings.delete("smtp.password")
    assert await repos.settings.get_secret("smtp.password") is None
