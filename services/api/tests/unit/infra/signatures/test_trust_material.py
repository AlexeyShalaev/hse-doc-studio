from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from hse_doc_studio.core.jobs.verify import OpenPgpTrustMode
from hse_doc_studio.core.signatures.errors import GpgError
from hse_doc_studio.infra.signatures import openpgp
from hse_doc_studio.infra.signatures.detached_verifier import DetachedSignatureVerifier
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.infra.signatures.trust_material import LocalTrustMaterialProvider, keys_digest

_ARMORED_SIG = b"-----BEGIN PGP SIGNATURE-----\n\nabc\n-----END PGP SIGNATURE-----\n"
_PUBLIC = b"-----BEGIN PGP PUBLIC KEY BLOCK-----\n\nxyz\n-----END PGP PUBLIC KEY BLOCK-----\n"
_needs_gpg = pytest.mark.skipif(
    shutil.which("gpg") is None or sys.platform == "win32",
    reason="gpg is not installed (or Windows, where gpg-agent does not start in CI)",
)


class _FakeKeyring(GpgKeyring):
    """Связка без gpg: издатели и выгрузка заданы тестом, запрошенные спецификации запоминаются."""

    def __init__(self, issuers: list[str], exported: bytes = _PUBLIC, fail: bool = False) -> None:
        super().__init__(Path("/nonexistent"), binary="gpg")
        self._issuers = issuers
        self._exported = exported
        self._fail = fail
        self.asked: list[list[str]] = []

    def signature_issuers(self, signature: bytes) -> list[str]:
        if self._fail:
            raise GpgError("broken")
        return self._issuers

    def export_public_keys(self, specs: Sequence[str] = ()) -> bytes:
        self.asked.append(list(specs))
        return self._exported


def _fill(roots: Path, cache: Path) -> None:
    roots.mkdir()
    cache.mkdir()
    (roots / "b.crt").write_bytes(b"root-b")
    (roots / "a.CER").write_bytes(b"root-a")
    (roots / "c.der").write_bytes(b"root-c")
    (roots / "d.pem").write_bytes(b"root-d")
    (roots / "notes.txt").write_bytes(b"skipped")
    (cache / "2.cer").write_bytes(b"inter-2")
    (cache / "1.cer").write_bytes(b"inter-1")
    (cache / "3.crt").write_bytes(b"skipped")


def test__trust_material__reads_roots_and_intermediates_like_verifier(tmp_path: Path) -> None:
    roots, cache = tmp_path / "trusted_roots", tmp_path / "chain_cache"
    _fill(roots, cache)
    verifier = DetachedSignatureVerifier(GpgKeyring(tmp_path / "gnupg"), roots, cache)

    bundle = LocalTrustMaterialProvider(roots, cache).snapshot()

    assert [b.to_bytes() for b in bundle.roots] == verifier.trusted_roots()
    assert [b.to_bytes() for b in bundle.intermediates] == verifier.intermediates()
    assert [b.to_bytes() for b in bundle.roots] == [b"root-a", b"root-b", b"root-c", b"root-d"]
    assert [b.to_bytes() for b in bundle.intermediates] == [b"inter-1", b"inter-2"]


def test__trust_material__no_signature__runner_home_without_keys(tmp_path: Path) -> None:
    bundle = LocalTrustMaterialProvider(tmp_path / "r", tmp_path / "c").snapshot()

    assert bundle.openpgp.mode is OpenPgpTrustMode.runner_home
    assert bundle.openpgp.keys == ()
    assert bundle.openpgp.digest == ""


def test__trust_material__missing_dirs_and_no_cache__empty(tmp_path: Path) -> None:
    assert LocalTrustMaterialProvider(tmp_path / "none", tmp_path / "none2").snapshot().roots == ()
    assert LocalTrustMaterialProvider(tmp_path / "none", None).snapshot().intermediates == ()


def test__trust_material__snapshot_is_taken_at_call_time(tmp_path: Path) -> None:
    roots, cache = tmp_path / "trusted_roots", tmp_path / "chain_cache"
    provider = LocalTrustMaterialProvider(roots, cache)
    assert provider.snapshot().roots == ()

    _fill(roots, cache)

    assert len(provider.snapshot().roots) == 4


def test__trust_material__openpgp_signature__does_not_touch_roots_or_cache(tmp_path: Path) -> None:
    roots = tmp_path / "r"
    roots.mkdir()
    (roots / "broken.pem").mkdir()  # папка с именем сертификата: чтение упало бы
    cache = tmp_path / "c"
    cache.mkdir()
    (cache / "x.cer").mkdir()
    provider = LocalTrustMaterialProvider(roots, cache)

    bundle = provider.snapshot(b"-----BEGIN PGP SIGNATURE-----\n\nabc")

    assert bundle.roots == ()
    assert bundle.intermediates == ()
    assert bundle.openpgp.mode is OpenPgpTrustMode.runner_home


def test__trust_material__cms_or_unknown_signature__still_reads_roots(tmp_path: Path) -> None:
    roots = tmp_path / "r"
    roots.mkdir()
    (roots / "a.pem").write_bytes(b"root")
    provider = LocalTrustMaterialProvider(roots, None)

    assert len(provider.snapshot(b"\x30\x82cms").roots) == 1
    assert len(provider.snapshot().roots) == 1


def test__trust_material__openpgp_issuer_known__inline_public_key_of_the_issuer(tmp_path: Path) -> None:
    keyring = _FakeKeyring(["A69C068EDAA6150C"])

    trust = LocalTrustMaterialProvider(tmp_path / "r", None, keyring).snapshot(_ARMORED_SIG).openpgp

    assert trust.mode is OpenPgpTrustMode.inline
    assert keyring.asked == [["A69C068EDAA6150C"]]
    assert [k.to_bytes() for k in trust.keys] == [_PUBLIC]
    assert trust.digest == keys_digest(trust.keys)
    assert len(trust.digest) == 64


def test__trust_material__openpgp_issuer_unreadable__exports_all_public_keys(tmp_path: Path) -> None:
    keyring = _FakeKeyring([])

    trust = LocalTrustMaterialProvider(tmp_path / "r", None, keyring).snapshot(_ARMORED_SIG).openpgp

    assert keyring.asked == [[]]
    assert trust.mode is OpenPgpTrustMode.inline
    assert len(trust.keys) == 1


def test__trust_material__openpgp_key_not_in_keyring__inline_without_keys(tmp_path: Path) -> None:
    trust = (
        LocalTrustMaterialProvider(tmp_path / "r", None, _FakeKeyring(["A69C068EDAA6150C"], exported=b""))
        .snapshot(_ARMORED_SIG)
        .openpgp
    )

    assert trust.mode is OpenPgpTrustMode.inline
    assert trust.keys == ()
    assert trust.digest == keys_digest(())


def test__trust_material__secret_material_in_export__never_sent(tmp_path: Path) -> None:
    leaked = b"-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nxyz\n-----END PGP PRIVATE KEY BLOCK-----\n"
    keyring = _FakeKeyring(["A69C068EDAA6150C"], exported=_PUBLIC + leaked)

    trust = LocalTrustMaterialProvider(tmp_path / "r", None, keyring).snapshot(_ARMORED_SIG).openpgp

    assert trust.keys == ()


def test__trust_material__gpg_fails_or_missing__runner_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    failing = LocalTrustMaterialProvider(tmp_path / "r", None, _FakeKeyring([], fail=True))
    monkeypatch.setattr(openpgp.shutil, "which", lambda *_a, **_kw: None)
    without_gpg = LocalTrustMaterialProvider(tmp_path / "r", None, GpgKeyring(tmp_path / "gnupg"))

    assert failing.snapshot(_ARMORED_SIG).openpgp.mode is OpenPgpTrustMode.runner_home
    assert without_gpg.snapshot(_ARMORED_SIG).openpgp.mode is OpenPgpTrustMode.runner_home


def test__trust_material__cms_signature__runner_home_and_keyring_untouched(tmp_path: Path) -> None:
    keyring = _FakeKeyring(["A69C068EDAA6150C"])

    bundle = LocalTrustMaterialProvider(tmp_path / "r", None, keyring).snapshot(b"\x30\x82cms")

    assert bundle.openpgp.mode is OpenPgpTrustMode.runner_home
    assert keyring.asked == []


@pytest.fixture
def ring() -> Iterator[GpgKeyring]:
    # Короткий /tmp ради длины пути сокета gpg-agent на macOS.
    home = Path(tempfile.mkdtemp(prefix="hds-tm-", dir="/tmp" if os.name == "posix" else None))
    keyring = GpgKeyring(home)
    yield keyring
    keyring.stop_agent()
    shutil.rmtree(home, ignore_errors=True)


@_needs_gpg
def test__trust_material__real_keyring__only_the_signer_public_key_is_sent(tmp_path: Path, ring: GpgKeyring) -> None:
    signer = ring.generate("Иван Иванов", "ivan@example.org")
    ring.generate("Научрук", "adv@example.org")
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"%PDF-1.7 content")
    ring.sign_detached(doc, signer.fingerprint, tmp_path / "doc.asc")

    trust = LocalTrustMaterialProvider(tmp_path / "r", None, ring).snapshot((tmp_path / "doc.asc").read_bytes())

    assert trust.openpgp.mode is OpenPgpTrustMode.inline
    [blob] = trust.openpgp.keys
    assert b"PRIVATE KEY" not in blob.to_bytes()
    receiver_home = Path(tempfile.mkdtemp(prefix="hds-tr-", dir="/tmp" if os.name == "posix" else None))
    receiver = GpgKeyring(receiver_home)
    try:
        imported = receiver.import_key(blob.to_bytes())
    finally:
        receiver.stop_agent()
        shutil.rmtree(receiver_home, ignore_errors=True)
    assert [(k.fingerprint, k.has_secret) for k in imported] == [(signer.fingerprint, False)]
