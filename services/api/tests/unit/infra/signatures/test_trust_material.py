from __future__ import annotations

from pathlib import Path

from hse_doc_studio.core.jobs.verify import OpenPgpTrustMode
from hse_doc_studio.infra.signatures.detached_verifier import DetachedSignatureVerifier
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring
from hse_doc_studio.infra.signatures.trust_material import LocalTrustMaterialProvider


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


def test__trust_material__stage_zero_openpgp_uses_runner_home_without_keys(tmp_path: Path) -> None:
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
