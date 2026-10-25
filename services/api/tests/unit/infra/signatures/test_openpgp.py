from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from hse_doc_studio.infra.signatures.openpgp import (
    GpgError,
    GpgKeyring,
    looks_like_openpgp_key,
    looks_like_openpgp_signature,
)

pytestmark = pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg is not installed")


@pytest.fixture
def ring(tmp_path_factory: pytest.TempPathFactory) -> Iterator[GpgKeyring]:
    home = Path("/tmp") / f"hds-gpg-{tmp_path_factory.mktemp('h').name}"
    r = GpgKeyring(home)
    try:
        yield r
    finally:
        r.stop_agent()
        shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def doc(tmp_path: Path) -> Path:
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.7 content")
    return p


def test_generate_sign_verify(ring: GpgKeyring, doc: Path, tmp_path: Path) -> None:
    key = ring.generate("Иван Иванов", "ivan@example.org")
    assert key.has_secret
    assert key.uids == ["Иван Иванов <ivan@example.org>"]
    assert not ring.is_protected(key.fingerprint)

    sig = tmp_path / "doc.pdf.asc"
    ring.sign_detached(doc, key.fingerprint, sig)
    assert looks_like_openpgp_signature(sig.read_bytes())

    result = ring.verify_detached(sig, doc)
    assert result.status == "good"
    assert result.fingerprint == key.fingerprint
    assert "ivan@example.org" in result.signer
    assert result.signed_at is not None


def test_verify_detects_modified_file(ring: GpgKeyring, doc: Path, tmp_path: Path) -> None:
    key = ring.generate("Иван Иванов", "ivan@example.org")
    sig = tmp_path / "doc.pdf.asc"
    ring.sign_detached(doc, key.fingerprint, sig)
    doc.write_bytes(doc.read_bytes() + b"!")
    assert ring.verify_detached(sig, doc).status == "bad"


def test_unknown_signer_then_import_public_key(ring: GpgKeyring, doc: Path, tmp_path: Path) -> None:
    other_home = Path("/tmp") / f"hds-gpg-other-{tmp_path.name}"
    other = GpgKeyring(other_home)
    try:
        key = other.generate("Научрук", "adv@example.org")
        sig = tmp_path / "doc.pdf.asc"
        other.sign_detached(doc, key.fingerprint, sig)
        public = other.export_public(key.fingerprint)
    finally:
        other.stop_agent()
        shutil.rmtree(other_home, ignore_errors=True)

    assert looks_like_openpgp_key(public)
    first = ring.verify_detached(sig, doc)
    assert first.status == "no_pubkey"
    assert first.key_id == key.key_id

    [imported] = ring.import_key(public)
    assert imported.fingerprint == key.fingerprint
    assert not imported.has_secret
    assert ring.verify_detached(sig, doc).status == "good"


def test_protected_key_needs_passphrase(ring: GpgKeyring, doc: Path, tmp_path: Path) -> None:
    key = ring.generate("Защищённый", "p@example.org", passphrase="s3cret")
    assert ring.is_protected(key.fingerprint)
    sig = tmp_path / "doc.asc"
    with pytest.raises(GpgError):
        ring.sign_detached(doc, key.fingerprint, sig, passphrase="wrong")
    ring.sign_detached(doc, key.fingerprint, sig, passphrase="s3cret")
    assert ring.verify_detached(sig, doc).status == "good"


def test_import_secret_key_roundtrip(ring: GpgKeyring, doc: Path, tmp_path: Path) -> None:
    src_home = Path("/tmp") / f"hds-gpg-src-{tmp_path.name}"
    src = GpgKeyring(src_home)
    try:
        key = src.generate("Импорт", "i@example.org")
        secret = src._run(
            ["--armor", "--pinentry-mode", "loopback", "--passphrase", "", "--export-secret-keys", key.fingerprint]
        ).stdout
    finally:
        src.stop_agent()
        shutil.rmtree(src_home, ignore_errors=True)
    assert looks_like_openpgp_key(secret)
    [imported] = ring.import_key(secret)
    assert imported.has_secret
    sig = tmp_path / "doc.asc"
    ring.sign_detached(doc, imported.fingerprint, sig)
    assert ring.verify_detached(sig, doc).status == "good"


def test_import_garbage_fails(ring: GpgKeyring) -> None:
    with pytest.raises(GpgError):
        ring.import_key(b"not a key")


def test_delete_key(ring: GpgKeyring) -> None:
    key = ring.generate("Удалить", "d@example.org")
    ring.delete(key.fingerprint)
    assert ring.get_key(key.fingerprint) is None


def test_deep_home_goes_through_short_symlink(tmp_path: Path) -> None:
    home = tmp_path / ("deep-" * 20) / "gnupg"
    ring = GpgKeyring(home)
    try:
        key = ring.generate("Глубокий", "deep@example.org")
        assert ring.get_key(key.fingerprint) is not None
    finally:
        ring.stop_agent()
