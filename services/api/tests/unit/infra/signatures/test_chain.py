from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import AuthorityInformationAccessOID, NameOID
from hse_doc_studio.infra.signatures import chain_fetcher
from hse_doc_studio.infra.signatures.chain_fetcher import ChainFetcher
from hse_doc_studio.infra.signatures.cms_inspector import inspect_cms

CONTENT = b"%PDF-1.7 chain test"
ISSUER_URL = "http://pki.example.org/root.cer"


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _make_chain() -> tuple[bytes, bytes]:
    """(CMS signature embedding only the leaf, DER of the self-signed root)."""
    now = datetime.now(timezone.utc)
    root_key = rsa.generate_private_key(65537, 2048)
    root = (
        x509.CertificateBuilder()
        .subject_name(_name("Test Root"))
        .issuer_name(_name("Test Root"))
        .public_key(root_key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(root_key, hashes.SHA256())
    )
    leaf_key = rsa.generate_private_key(65537, 2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(_name("Петров Пётр"))
        .issuer_name(_name("Test Root"))
        .public_key(leaf_key.public_key())
        .serial_number(2)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.AuthorityInformationAccess(
                [
                    x509.AccessDescription(
                        AuthorityInformationAccessOID.CA_ISSUERS, x509.UniformResourceIdentifier(ISSUER_URL)
                    )
                ]
            ),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )
    sig = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(CONTENT)
        .add_signer(leaf, leaf_key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
    )
    return sig, root.public_bytes(serialization.Encoding.DER)


def test_missing_issuer_is_incomplete_until_fetched_then_untrusted_root_with_its_fingerprint() -> None:
    sig, root_der = _make_chain()

    [bare] = inspect_cms(sig, CONTENT)
    assert bare.chain == "incomplete"

    [with_root] = inspect_cms(sig, CONTENT, intermediates=[root_der])
    assert with_root.chain == "untrusted_root"
    assert with_root.chain_root_subject == "Test Root"
    assert with_root.chain_root_fingerprint == hashlib.sha256(root_der).hexdigest()
    # An intermediate never grants trust by itself; only a trusted root does.
    [trusted] = inspect_cms(sig, CONTENT, trusted_roots=[root_der])
    assert trusted.chain == "trusted"
    assert trusted.chain_root_fingerprint == ""


def test_fetcher_follows_aia_and_caches_the_issuer(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    sig, root_der = _make_chain()
    monkeypatch.setattr(chain_fetcher, "_is_public_http", lambda url: True)
    monkeypatch.setattr(
        chain_fetcher.httpx,
        "get",
        lambda url, **kw: httpx.Response(200, content=root_der, request=httpx.Request("GET", url)),
    )
    fetcher = ChainFetcher(tmp_path / "cache")

    fetched = fetcher.complete(sig)

    fingerprint = hashlib.sha256(root_der).hexdigest()
    assert fetched == [fingerprint]
    assert fetcher.load(fingerprint) == root_der
    assert fetcher.load("../../etc/passwd") is None


def test_fetcher_refuses_private_hosts(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    sig, _ = _make_chain()
    called: list[str] = []
    monkeypatch.setattr(chain_fetcher.httpx, "get", lambda url, **kw: called.append(url))
    monkeypatch.setattr(chain_fetcher, "_is_public_http", lambda url: False)

    assert ChainFetcher(tmp_path / "cache").complete(sig) == []
    assert called == []


def test_public_http_check_rejects_loopback_and_bad_schemes() -> None:
    assert not chain_fetcher._is_public_http("http://127.0.0.1/x.cer")
    assert not chain_fetcher._is_public_http("file:///etc/passwd")
    assert not chain_fetcher._is_public_http("ftp://example.org/x")
