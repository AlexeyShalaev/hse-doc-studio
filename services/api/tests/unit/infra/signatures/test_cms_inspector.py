from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID
from hse_doc_studio.infra.signatures.cms_inspector import CmsParseError, inspect_cms, looks_like_cms

from .gost_fixture import make_detached_cms, make_identity

CONTENT = b"%PDF-1.7 fake body for signing"


def _classic_identity(kind: str) -> tuple[x509.Certificate, object]:
    key: object = rsa.generate_private_key(65537, 2048) if kind == "rsa" else ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Петров Пётр")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())  # type: ignore[attr-defined]
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())  # type: ignore[arg-type]
    )
    return cert, key


def _cms(kind: str, content: bytes = CONTENT) -> tuple[bytes, x509.Certificate]:
    cert, key = _classic_identity(kind)
    sig = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(content)
        .add_signer(cert, key, hashes.SHA256())  # type: ignore[arg-type]
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
    )
    return sig, cert


@pytest.mark.parametrize("kind", ["rsa", "ec"])
def test_classic_signature_valid(kind: str) -> None:
    sig, _ = _cms(kind)
    [report] = inspect_cms(sig, CONTENT)
    assert report.verdict == "valid"
    assert report.digest_match is True
    assert report.signature_valid is True
    assert report.subject == "Петров Пётр"
    assert report.cert_valid_at_signing is True
    assert report.chain == "untrusted_root"


@pytest.mark.parametrize("kind", ["rsa", "ec"])
def test_classic_signature_detects_modified_file(kind: str) -> None:
    sig, _ = _cms(kind)
    [report] = inspect_cms(sig, CONTENT + b"!")
    assert report.verdict == "invalid"
    assert report.digest_match is False


def test_self_signed_root_becomes_trusted_when_supplied() -> None:
    sig, cert = _cms("rsa")
    root = cert.public_bytes(serialization.Encoding.DER)
    [report] = inspect_cms(sig, CONTENT, trusted_roots=[root])
    assert report.chain == "trusted"


def test_gost_signature_valid() -> None:
    ident = make_identity()
    sig = make_detached_cms(ident, CONTENT)
    [report] = inspect_cms(sig, CONTENT)
    assert report.verdict == "valid"
    assert report.digest_match is True
    assert report.signature_valid is True
    assert report.subject == "Иванов Иван Иванович"
    assert report.subject_fields["snils"] == "12345678901"
    assert report.digest_algorithm == "1.2.643.7.1.1.2.2"
    assert report.signed_at == datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    assert report.fingerprint_sha256 == hashlib.sha256(ident.cert_der).hexdigest()
    assert report.chain == "untrusted_root"


def test_gost_signature_detects_modified_file() -> None:
    sig = make_detached_cms(make_identity(), CONTENT)
    [report] = inspect_cms(sig, CONTENT + b"!")
    assert report.verdict == "invalid"
    assert report.digest_match is False


def test_gost_signature_detects_forged_signature_value() -> None:
    sig = bytearray(make_detached_cms(make_identity(), CONTENT))
    sig[-1] ^= 0xFF  # last byte belongs to the signature OCTET STRING
    [report] = inspect_cms(bytes(sig), CONTENT)
    assert report.digest_match is True
    assert report.signature_valid is False
    assert report.verdict == "invalid"


def test_pem_input_is_accepted() -> None:
    import base64  # noqa: PLC0415

    sig = make_detached_cms(make_identity(), CONTENT)
    body = base64.encodebytes(sig).decode()
    pem = f"-----BEGIN PKCS7-----\n{body}-----END PKCS7-----\n".encode()
    assert looks_like_cms(pem)
    [report] = inspect_cms(pem, CONTENT)
    assert report.verdict == "valid"


def test_garbage_is_rejected(tmp_path: Path) -> None:
    assert not looks_like_cms(b"-----BEGIN PGP SIGNATURE-----\n")
    with pytest.raises(CmsParseError):
        inspect_cms(b"\x30\x03\x02\x01\x01", CONTENT)


def test_describe_certificate_reads_owner_serial_and_validity() -> None:
    from hse_doc_studio.infra.signatures.cms_inspector import describe_certificate  # noqa: PLC0415

    ident = make_identity("Петрова Анна")
    info = describe_certificate(ident.cert_der)
    assert info.owner == "Петрова Анна"
    assert info.serial == format(ident.serial, "X")
    assert info.not_after.year == 2049
    assert info.qualified_hint is False
