"""Политика серверных ключей для OpenPGP: создать и загрузить секретный ключ можно только при разрешении админа."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.entities import SigningIdentity, SigningKeyMaterial
from hse_doc_studio.core.signatures.key_policy import LocalSigningKeyPolicy, SigningKeyStorageDeniedError
from hse_doc_studio.infra.signatures.openpgp import GpgKey, GpgKeyring
from hse_doc_studio.use_cases.signing_identities.openpgp_keys import (
    CreateOpenPgpKeyInput,
    CreateOpenPgpKeyUC,
    ImportOpenPgpKeyInput,
    ImportOpenPgpKeyUC,
)

pytestmark = pytest.mark.unit

_SECRET_FPR = "A" * 40
_PUBLIC_FPR = "B" * 40


def _key(fingerprint: str, *, secret: bool) -> GpgKey:
    return GpgKey(fingerprint, fingerprint[-16:], ["Иван <i@example.org>"], secret, "ed25519", datetime.now(UTC), None)


class _Policy:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed = allowed

    async def server_key_storage_allowed(self) -> bool:
        return self.allowed


class _Repo:
    def __init__(self) -> None:
        self.created: list[SigningIdentity] = []

    async def list_all(self) -> list[SigningIdentity]:
        return list(self.created)

    async def create(self, identity: SigningIdentity, material: SigningKeyMaterial | None = None) -> None:
        self.created.append(identity)


class _Keyring:
    """Связка без gpg: файл `secret` несёт секретный ключ, `public` только открытый."""

    def __init__(self) -> None:
        self.generated = 0
        self.imported: list[bytes] = []

    def generate(self, name: str, email: str, passphrase: str = "") -> GpgKey:
        self.generated += 1
        return _key(_SECRET_FPR, secret=True)

    def contains_secret_key(self, data: bytes) -> bool:
        return data == b"secret"

    def import_key(self, data: bytes, passphrase: str | None = None) -> list[GpgKey]:
        self.imported.append(data)
        return [_key(_SECRET_FPR, secret=True)] if data == b"secret" else [_key(_PUBLIC_FPR, secret=False)]

    def is_protected(self, fingerprint: str) -> bool:
        return False


def _create(policy: Any) -> tuple[CreateOpenPgpKeyUC, _Repo, _Keyring]:
    repo, keyring = _Repo(), _Keyring()
    return CreateOpenPgpKeyUC(repo, keyring, policy), repo, keyring  # type: ignore[arg-type]


def _import(policy: Any) -> tuple[ImportOpenPgpKeyUC, _Repo, _Keyring]:
    repo, keyring = _Repo(), _Keyring()
    return ImportOpenPgpKeyUC(repo, keyring, policy), repo, keyring  # type: ignore[arg-type]


async def test__create_openpgp__storage_forbidden__refused_before_gpg_generates_anything() -> None:
    uc, repo, keyring = _create(_Policy(allowed=False))

    with pytest.raises(SigningKeyStorageDeniedError):
        await uc.execute(CreateOpenPgpKeyInput(name="Иван"))

    assert keyring.generated == 0
    assert repo.created == []


@pytest.mark.parametrize("policy", [_Policy(allowed=True), LocalSigningKeyPolicy()], ids=["server-allowed", "local"])
async def test__create_openpgp__storage_allowed_or_local__key_becomes_an_identity(policy: Any) -> None:
    uc, repo, keyring = _create(policy)

    out = await uc.execute(CreateOpenPgpKeyInput(name="Иван", passphrase="pw"))

    assert keyring.generated == 1
    assert [i.fingerprint for i in repo.created] == [_SECRET_FPR]
    assert out.identity.protected


async def test__import_openpgp__storage_forbidden__secret_key_refused_before_the_keyring_import() -> None:
    uc, repo, keyring = _import(_Policy(allowed=False))

    with pytest.raises(SigningKeyStorageDeniedError):
        await uc.execute(ImportOpenPgpKeyInput(data=b"secret"))

    assert keyring.imported == []
    assert repo.created == []


async def test__import_openpgp__storage_forbidden__public_key_is_still_imported() -> None:
    uc, repo, keyring = _import(_Policy(allowed=False))

    out = await uc.execute(ImportOpenPgpKeyInput(data=b"public"))

    assert keyring.imported == [b"public"]
    assert [k.fingerprint for k in out.public_keys] == [_PUBLIC_FPR]
    assert out.identities == []
    assert repo.created == []


@pytest.mark.parametrize("policy", [_Policy(allowed=True), LocalSigningKeyPolicy()], ids=["server-allowed", "local"])
async def test__import_openpgp__storage_allowed_or_local__secret_key_becomes_an_identity(policy: Any) -> None:
    uc, repo, keyring = _import(policy)

    out = await uc.execute(ImportOpenPgpKeyInput(data=b"secret"))

    assert keyring.imported == [b"secret"]
    assert [i.fingerprint for i in out.identities] == [_SECRET_FPR]
    assert [i.fingerprint for i in repo.created] == [_SECRET_FPR]


# Настоящий gpg: после отказа секретной части в общей связке нет, а открытый ключ из того же экспорта входит.
_needs_gpg = pytest.mark.skipif(
    shutil.which("gpg") is None or sys.platform == "win32",
    reason="gpg is not installed (or Windows, where gpg-agent does not start in CI)",
)


def _ring(name: str) -> GpgKeyring:
    return GpgKeyring(Path("/tmp") / f"hds-gpg-{name}")


@pytest.fixture
def rings(tmp_path: Path) -> Iterator[tuple[GpgKeyring, GpgKeyring]]:
    shared, source = _ring(f"shared-{tmp_path.name}"), _ring(f"source-{tmp_path.name}")
    try:
        yield shared, source
    finally:
        for ring in (shared, source):
            ring.stop_agent()
            shutil.rmtree(ring._home, ignore_errors=True)  # noqa: SLF001


@_needs_gpg
async def test__import_openpgp__storage_forbidden__real_keyring_keeps_no_secret_but_takes_the_public_key(
    rings: tuple[GpgKeyring, GpgKeyring],
) -> None:
    shared, source = rings
    key = source.generate("Иван", "i@example.org")
    secret = source._run(  # noqa: SLF001
        ["--armor", "--pinentry-mode", "loopback", "--passphrase", "", "--export-secret-keys", key.fingerprint]
    ).stdout
    public = source.export_public(key.fingerprint)
    uc = ImportOpenPgpKeyUC(_Repo(), shared, _Policy(allowed=False))  # type: ignore[arg-type]

    with pytest.raises(SigningKeyStorageDeniedError):
        await uc.execute(ImportOpenPgpKeyInput(data=secret))
    assert shared.list_keys() == []

    out = await uc.execute(ImportOpenPgpKeyInput(data=public))
    assert [k.fingerprint for k in out.public_keys] == [key.fingerprint]
    assert [k.has_secret for k in shared.list_keys()] == [False]
