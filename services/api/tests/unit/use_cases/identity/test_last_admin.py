from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.use_cases.admin.last_admin import ensure_admin_remains

from tests.fakes.identity import InMemoryIdentityStore, InMemoryUserRepository
from tests.unit.use_cases.identity.conftest import T0


def _user(uid: str, *, admin: bool, status: UserStatus = UserStatus.active) -> User:
    email = f"{uid}@example.org"
    return User(
        id=uid,
        email=email,
        email_normalized=normalize_email(email),
        name=uid,
        status=status,
        created_at=T0,
        is_instance_admin=admin,
    )


async def _repo(*users: User) -> InMemoryUserRepository:
    repo = InMemoryUserRepository(InMemoryIdentityStore())
    for user in users:
        await repo.add(user)
    return repo


async def test__ensure_admin_remains__last_admin_demoted__refused() -> None:
    admin = _user("a", admin=True)
    repo = await _repo(admin, _user("m", admin=False))

    with pytest.raises(IdentityError) as err:
        await ensure_admin_remains(repo, admin, replace(admin, is_instance_admin=False))

    assert err.value.code is IdentityErrorCode.last_admin


async def test__ensure_admin_remains__last_admin_disabled_or_deleted__refused() -> None:
    admin = _user("a", admin=True)
    repo = await _repo(admin)

    for after in (replace(admin, status=UserStatus.disabled), None):
        with pytest.raises(IdentityError):
            await ensure_admin_remains(repo, admin, after)


async def test__ensure_admin_remains__disabled_admin_does_not_count() -> None:
    admin = _user("a", admin=True)
    repo = await _repo(admin, _user("b", admin=True, status=UserStatus.disabled))

    with pytest.raises(IdentityError):
        await ensure_admin_remains(repo, admin, None)


async def test__ensure_admin_remains__other_admin_exists__allowed() -> None:
    admin = _user("a", admin=True)
    repo = await _repo(admin, _user("b", admin=True))

    await ensure_admin_remains(repo, admin, None)
    await ensure_admin_remains(repo, admin, replace(admin, is_instance_admin=False))


async def test__ensure_admin_remains__not_an_admin_or_still_admin__allowed() -> None:
    admin = _user("a", admin=True)
    member = _user("m", admin=False)
    repo = await _repo(admin, member)

    await ensure_admin_remains(repo, member, None)
    await ensure_admin_remains(repo, admin, replace(admin, name="Новое имя"))
