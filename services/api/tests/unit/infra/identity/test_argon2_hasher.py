from __future__ import annotations

import pytest
from argon2 import PasswordHasher
from hse_doc_studio.infra.identity.argon2_hasher import Argon2PasswordHasher

_FAST = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


@pytest.mark.parametrize("password", ["correct horse battery", "пароль-с-юникодом-🔑", "x" * 256])
def test_hash_verify_roundtrip(password: str) -> None:
    hasher = Argon2PasswordHasher(_FAST)
    hashed = hasher.hash(password)
    assert hashed.startswith("$argon2id$")
    assert hasher.verify(password, hashed)
    assert not hasher.verify(password + "!", hashed)


def test_verify_garbage_hash_is_false() -> None:
    assert not Argon2PasswordHasher(_FAST).verify("pw", "not-a-hash")


def test_needs_rehash_when_params_change() -> None:
    old = Argon2PasswordHasher(_FAST).hash("password-1234")
    current = Argon2PasswordHasher(PasswordHasher(time_cost=2, memory_cost=8, parallelism=1))
    assert current.needs_rehash(old)
    assert not current.needs_rehash(current.hash("password-1234"))
    assert current.needs_rehash("garbage")
