from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from hse_doc_studio.core.enums import DetachedFormat, DetachedVerdict
from hse_doc_studio.infra.signatures.detached_verifier import (
    DetachedSignatureVerifier,
    UnknownSignatureFormatError,
    detect_format,
)
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring

from .gost_fixture import make_detached_cms, make_identity


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.7 body")
    return p


@pytest.fixture
def ring() -> Iterator[GpgKeyring]:
    import tempfile  # noqa: PLC0415

    home = Path(tempfile.mkdtemp(prefix="hds-v-", dir="/tmp"))
    r = GpgKeyring(home)
    yield r
    r.stop_agent()
    shutil.rmtree(home, ignore_errors=True)


def test_gost_cms_valid_and_notes(pdf: Path, tmp_path: Path, ring: GpgKeyring) -> None:
    v = DetachedSignatureVerifier(ring, tmp_path / "roots")
    sig = make_detached_cms(make_identity(), pdf.read_bytes())
    assert detect_format(sig) is DetachedFormat.cms
    out = v.verify(pdf, sig)
    assert out.verdict is DetachedVerdict.valid
    assert out.signer == "Иванов Иван Иванович"
    assert out.extension == ".p7s"
    assert "chain_untrusted_root" in out.notes
    assert "no_revocation_check" in out.notes


def test_cms_for_other_file_is_invalid(pdf: Path, tmp_path: Path, ring: GpgKeyring) -> None:
    v = DetachedSignatureVerifier(ring, tmp_path / "roots")
    sig = make_detached_cms(make_identity(), b"some other file")
    assert v.verify(pdf, sig).verdict is DetachedVerdict.invalid


def test_trusted_root_dir_is_used(pdf: Path, tmp_path: Path, ring: GpgKeyring) -> None:
    roots = tmp_path / "roots"
    roots.mkdir()
    ident = make_identity()
    (roots / "root.cer").write_bytes(ident.cert_der)
    v = DetachedSignatureVerifier(ring, roots)
    out = v.verify(pdf, make_detached_cms(ident, pdf.read_bytes()))
    assert out.chain == "trusted"
    assert "chain_untrusted_root" not in out.notes


@pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg is not installed")
def test_openpgp_flow(pdf: Path, tmp_path: Path, ring: GpgKeyring) -> None:
    key = ring.generate("Иван", "i@example.org")
    sig_path = tmp_path / "doc.asc"
    ring.sign_detached(pdf, key.fingerprint, sig_path)
    v = DetachedSignatureVerifier(ring, tmp_path / "roots")
    out = v.verify(pdf, sig_path.read_bytes())
    assert out.format is DetachedFormat.openpgp
    assert out.verdict is DetachedVerdict.valid
    assert out.signer_id == key.fingerprint
    assert out.extension == ".asc"

    pdf.write_bytes(pdf.read_bytes() + b"!")
    assert v.verify(pdf, sig_path.read_bytes()).verdict is DetachedVerdict.invalid


def test_unknown_format_rejected(pdf: Path, tmp_path: Path, ring: GpgKeyring) -> None:
    v = DetachedSignatureVerifier(ring, tmp_path / "roots")
    with pytest.raises(UnknownSignatureFormatError):
        v.verify(pdf, b"plain text, not a signature")
