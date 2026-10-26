"""VerifyDetachedHandler: проверка открепленной подписи как задача."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import DetachedFormat, DetachedVerdict, Lang
from hse_doc_studio.core.jobs.enums import JobErrorCategory
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.files import InlineBlob, ManifestFile
from hse_doc_studio.core.jobs.protocols import JobContext
from hse_doc_studio.core.jobs.verify import (
    CODE_GPG_UNAVAILABLE,
    CODE_OPENPGP_INLINE_UNSUPPORTED,
    CODE_UNKNOWN_SIGNATURE_FORMAT,
    OpenPgpTrust,
    OpenPgpTrustMode,
    TrustBundle,
    VerifyDetachedPayload,
    VerifyDetachedResult,
)
from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs
from hse_doc_studio.infra.jobs.verify_detached import VerifyDetachedHandler
from hse_doc_studio.infra.signatures import openpgp
from hse_doc_studio.infra.signatures.detached_verifier import DetachedSignatureVerifier
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring

from tests.unit.core.jobs.samples import JOB_ID, PROJECT_ID
from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity

_PDF = "docs/Аннотация.pdf"
_needs_gpg = pytest.mark.skipif(
    shutil.which("gpg") is None or sys.platform == "win32",
    reason="gpg is not installed (or Windows, where gpg-agent does not start in CI)",
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "docs").mkdir(parents=True)
    (root / _PDF).write_bytes(b"%PDF-1.7 body")
    return root


@pytest.fixture
def ring(tmp_path: Path) -> Iterator[GpgKeyring]:
    # Короткий /tmp ради длины пути сокета gpg-agent на macOS.
    home = Path(tempfile.mkdtemp(prefix="hds-vh-", dir="/tmp" if os.name == "posix" else None))
    keyring = GpgKeyring(home)
    yield keyring
    keyring.stop_agent()
    shutil.rmtree(home, ignore_errors=True)


def _handler(ring: GpgKeyring, tmp_path: Path) -> VerifyDetachedHandler:
    return VerifyDetachedHandler(DetachedSignatureVerifier(ring, tmp_path / "unused-roots"))


def _ctx(workspace: Path) -> JobContext:
    return JobContext(
        job_id=JOB_ID,
        project_id=PROJECT_ID,
        actor=Actor.local(),
        locale=Lang.ru,
        workspace=workspace,
        outputs=LocalJobOutputs(),
    )


def _payload(signature: bytes, trust: TrustBundle | None = None, pdf: str = _PDF) -> VerifyDetachedPayload:
    return VerifyDetachedPayload(
        pdf=ManifestFile(pdf),
        signature=InlineBlob.from_bytes(signature),
        trust=trust or TrustBundle(),
    )


async def test__verify_handler__cms_gost_valid_untrusted_root(
    workspace: Path, tmp_path: Path, ring: GpgKeyring
) -> None:
    sig = make_detached_cms(make_identity(), (workspace / _PDF).read_bytes())

    result = await _handler(ring, tmp_path).handle(_payload(sig), _ctx(workspace))

    assert isinstance(result, VerifyDetachedResult)
    verified = result.signature
    assert verified.format is DetachedFormat.cms
    assert verified.verdict is DetachedVerdict.valid
    assert verified.signer == "Иванов Иван Иванович"
    assert "chain_untrusted_root" in verified.notes


async def test__verify_handler__roots_from_payload_make_the_chain_trusted(
    workspace: Path, tmp_path: Path, ring: GpgKeyring
) -> None:
    ident = make_identity()
    sig = make_detached_cms(ident, (workspace / _PDF).read_bytes())
    trust = TrustBundle(roots=(InlineBlob.from_bytes(ident.cert_der),))

    result = await _handler(ring, tmp_path).handle(_payload(sig, trust), _ctx(workspace))

    assert isinstance(result, VerifyDetachedResult)
    assert result.signature.chain == "trusted"
    assert "chain_untrusted_root" not in result.signature.notes


async def test__verify_handler__signature_of_other_content__invalid_verdict_is_a_result(
    workspace: Path, tmp_path: Path, ring: GpgKeyring
) -> None:
    sig = make_detached_cms(make_identity(), b"some other file")

    result = await _handler(ring, tmp_path).handle(_payload(sig), _ctx(workspace))

    assert isinstance(result, VerifyDetachedResult)
    assert result.signature.verdict is DetachedVerdict.invalid


async def test__verify_handler__garbage__invalid_input_code(workspace: Path, tmp_path: Path, ring: GpgKeyring) -> None:
    with pytest.raises(JobFailure) as caught:
        await _handler(ring, tmp_path).handle(_payload(b"plain text, not a signature"), _ctx(workspace))

    error = caught.value.error
    assert error.category is JobErrorCategory.invalid_input
    assert error.code == CODE_UNKNOWN_SIGNATURE_FORMAT
    assert error.detail == "not an OpenPGP or CMS signature"


async def test__verify_handler__gpg_missing__unavailable_code(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_which = shutil.which
    monkeypatch.setattr(
        openpgp.shutil, "which", lambda cmd, *a, **kw: None if cmd == "gpg" else real_which(cmd, *a, **kw)
    )
    ring = GpgKeyring(tmp_path / "gnupg")
    armored = b"-----BEGIN PGP SIGNATURE-----\n\nabcd\n-----END PGP SIGNATURE-----\n"

    with pytest.raises(JobFailure) as caught:
        await _handler(ring, tmp_path).handle(_payload(armored), _ctx(workspace))

    assert caught.value.error.category is JobErrorCategory.unavailable
    assert caught.value.error.code == CODE_GPG_UNAVAILABLE


@_needs_gpg
async def test__verify_handler__openpgp_known_key_good_and_unknown_key(
    workspace: Path, tmp_path: Path, ring: GpgKeyring
) -> None:
    key = ring.generate("Иван", "i@example.org")
    sig_path = tmp_path / "doc.asc"
    ring.sign_detached(workspace / _PDF, key.fingerprint, sig_path)
    signature = sig_path.read_bytes()
    foreign_home = Path(tempfile.mkdtemp(prefix="hds-vf-", dir="/tmp" if os.name == "posix" else None))
    foreign = GpgKeyring(foreign_home)
    try:
        known = await _handler(ring, tmp_path).handle(_payload(signature), _ctx(workspace))
        unknown = await _handler(foreign, tmp_path).handle(_payload(signature), _ctx(workspace))
    finally:
        foreign.stop_agent()
        shutil.rmtree(foreign_home, ignore_errors=True)

    assert isinstance(known, VerifyDetachedResult)
    assert known.signature.format is DetachedFormat.openpgp
    assert known.signature.verdict is DetachedVerdict.valid
    assert known.signature.signer_id == key.fingerprint
    assert isinstance(unknown, VerifyDetachedResult)
    assert unknown.signature.verdict is DetachedVerdict.unknown_key
    assert unknown.signature.missing_key_id


async def test__verify_handler__inline_openpgp_mode__rejected(
    workspace: Path, tmp_path: Path, ring: GpgKeyring
) -> None:
    sig = make_detached_cms(make_identity(), (workspace / _PDF).read_bytes())
    trust = TrustBundle(openpgp=OpenPgpTrust(mode=OpenPgpTrustMode.inline, digest="ab12"))

    with pytest.raises(JobFailure) as caught:
        await _handler(ring, tmp_path).handle(_payload(sig, trust), _ctx(workspace))

    assert caught.value.error.category is JobErrorCategory.internal
    assert caught.value.error.code == CODE_OPENPGP_INLINE_UNSUPPORTED


async def test__verify_handler__pdf_outside_workspace__rejected(
    workspace: Path, tmp_path: Path, ring: GpgKeyring
) -> None:
    (workspace.parent / "outside.pdf").write_bytes(b"%PDF")
    (workspace / "link.pdf").symlink_to(workspace.parent / "outside.pdf")

    with pytest.raises(ValueError, match="escapes the workspace"):
        await _handler(ring, tmp_path).handle(_payload(b"x", pdf="link.pdf"), _ctx(workspace))
