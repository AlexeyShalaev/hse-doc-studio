"""PublicKeyReader: сертификат и открытый ключ OpenPGP принимаются, закрытый ключ в любом виде нет."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from hse_doc_studio.core.signatures.signer_profile import PublicKeyKind, SecretKeyMaterialError
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.infra.signatures.public_key_reader import PublicKeyReader

from tests.fakes.signer_profile import SelfSigned, make_self_signed

_NO_GPG = pytest.mark.skipif(
    shutil.which("gpg") is None or sys.platform == "win32",
    reason="gpg is not installed (or Windows, where gpg-agent does not start in CI)",
)


@dataclass(frozen=True)
class OpenPgpPair:
    public: bytes
    secret: bytes
    secret_binary: bytes
    fingerprint: str


@pytest.fixture(scope="module")
def x509_pair() -> SelfSigned:
    return make_self_signed("Петров Пётр", serial=0x1A2B3C)


def _short_home(tmp_path_factory: pytest.TempPathFactory, prefix: str) -> Path:
    # Сокет gpg-agent не помещается в длинный путь временного каталога: связка лежит в /tmp.
    return Path("/tmp") / f"{prefix}-{tmp_path_factory.mktemp('h').name}"


@pytest.fixture(scope="module")
def openpgp_pair(tmp_path_factory: pytest.TempPathFactory) -> Iterator[OpenPgpPair]:
    if shutil.which("gpg") is None or sys.platform == "win32":
        pytest.skip("gpg is not installed")
    home = _short_home(tmp_path_factory, "hds-sp-src")
    src = GpgKeyring(home)
    try:
        key = src.generate("Пётр Петров", "petrov@example.org")
        secret_args = ["--pinentry-mode", "loopback", "--passphrase", "", "--export-secret-keys", key.fingerprint]
        yield OpenPgpPair(
            public=src.export_public(key.fingerprint),
            secret=src._run(["--armor", *secret_args]).stdout,
            secret_binary=src._run(secret_args).stdout,
            fingerprint=key.fingerprint,
        )
    finally:
        src.stop_agent()
        shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def ring(tmp_path_factory: pytest.TempPathFactory) -> Iterator[GpgKeyring]:
    home = _short_home(tmp_path_factory, "hds-sp")
    keyring = GpgKeyring(home)
    try:
        yield keyring
    finally:
        keyring.stop_agent()
        shutil.rmtree(home, ignore_errors=True)


class _NoGpg:
    available = False

    def contains_secret_key(self, data: bytes) -> bool:
        raise AssertionError("gpg is not called without gpg")

    def show_keys(self, data: bytes) -> list[object]:
        raise AssertionError("gpg is not called without gpg")


@pytest.mark.parametrize("form", ["pem", "der"])
async def test__read__certificate__plate_from_the_certificate_and_pem_stored(x509_pair: SelfSigned, form: str) -> None:
    blob = x509_pair.cert_pem if form == "pem" else x509_pair.cert_der

    data = await PublicKeyReader(_NoGpg()).read(blob)  # type: ignore[arg-type]

    assert data.kind is PublicKeyKind.x509
    assert data.data == x509_pair.cert_pem
    assert (data.plate.kind, data.plate.owner, data.plate.cert_id) == ("x509", "Петров Пётр", "1A2B3C")
    assert len(data.plate.signer_id) == 64


async def test__read__certificate_with_trailing_bytes__only_the_certificate_is_kept(
    x509_pair: SelfSigned,
) -> None:
    data = await PublicKeyReader(_NoGpg()).read(x509_pair.cert_der + b"tail")  # type: ignore[arg-type]

    assert data.data == x509_pair.cert_pem


@pytest.mark.parametrize("variant", ["key-only", "cert-then-key", "key-then-cert", "rsa-header", "encrypted-header"])
async def test__read__pem_with_a_private_key__refused(x509_pair: SelfSigned, variant: str) -> None:
    blob = {
        "key-only": x509_pair.key_pem,
        "cert-then-key": x509_pair.cert_pem + x509_pair.key_pem,
        "key-then-cert": x509_pair.key_pem + x509_pair.cert_pem,
        "rsa-header": b"-----BEGIN RSA PRIVATE KEY-----\nAAAA\n-----END RSA PRIVATE KEY-----\n" + x509_pair.cert_pem,
        "encrypted-header": b"-----BEGIN ENCRYPTED PRIVATE KEY-----\nAAAA\n-----END ENCRYPTED PRIVATE KEY-----\n",
    }[variant]

    with pytest.raises(SecretKeyMaterialError):
        await PublicKeyReader(_NoGpg()).read(blob)  # type: ignore[arg-type]


async def test__read__pkcs12_container__refused_as_a_private_key(x509_pair: SelfSigned) -> None:
    with pytest.raises(SecretKeyMaterialError):
        await PublicKeyReader(_NoGpg()).read(x509_pair.p12)  # type: ignore[arg-type]


async def test__read__empty_or_huge__refused_before_parsing() -> None:
    with pytest.raises(ValueError, match="пустой|Empty"):
        await PublicKeyReader(_NoGpg()).read(b"")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="большой|large"):
        await PublicKeyReader(_NoGpg()).read(b"x" * (128 * 1024 + 1))  # type: ignore[arg-type]


async def test__read__not_a_certificate_and_no_gpg__says_so() -> None:
    with pytest.raises(ValueError, match="gpg"):
        await PublicKeyReader(_NoGpg()).read(b"-----BEGIN PGP PUBLIC KEY BLOCK-----\n\nAAAA\n")  # type: ignore[arg-type]


@_NO_GPG
async def test__read__openpgp_public_key__plate_from_the_key_and_nothing_imported(
    openpgp_pair: OpenPgpPair, ring: GpgKeyring
) -> None:
    data = await PublicKeyReader(ring).read(openpgp_pair.public)

    assert data.kind is PublicKeyKind.openpgp
    assert data.data == openpgp_pair.public
    assert (data.plate.kind, data.plate.owner, data.plate.signer_id) == (
        "openpgp",
        "Пётр Петров",
        openpgp_pair.fingerprint,
    )
    assert ring.list_keys() == []


@_NO_GPG
@pytest.mark.parametrize("variant", ["armored", "binary", "under-public-header", "public-then-secret"])
async def test__read__openpgp_secret_key__refused_and_keyring_stays_empty(
    openpgp_pair: OpenPgpPair, ring: GpgKeyring, variant: str
) -> None:
    blob = {
        "armored": openpgp_pair.secret,
        "binary": openpgp_pair.secret_binary,
        "under-public-header": openpgp_pair.secret.replace(b"PRIVATE KEY BLOCK", b"PUBLIC KEY BLOCK"),
        "public-then-secret": openpgp_pair.public + openpgp_pair.secret,
    }[variant]

    with pytest.raises(SecretKeyMaterialError):
        await PublicKeyReader(ring).read(blob)

    assert ring.list_keys() == []


@_NO_GPG
async def test__read__two_public_keys__refused(openpgp_pair: OpenPgpPair, ring: GpgKeyring) -> None:
    other = ring.generate("Другой", "other@example.org")
    second = ring.export_public(other.fingerprint)

    with pytest.raises(ValueError, match="несколько|several"):
        await PublicKeyReader(ring).read(openpgp_pair.public + second)


@_NO_GPG
async def test__read__junk__neither_certificate_nor_key(ring: GpgKeyring) -> None:
    with pytest.raises(ValueError, match="X.509"):
        await PublicKeyReader(ring).read(b"just some text")
