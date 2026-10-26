from __future__ import annotations

import base64
import hashlib
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.infra.git_sync.tls_certificates import TlsCertificateService, certificate_fingerprint

from tests.fixtures.git_remote import GitHttpServer
from tests.fixtures.tls import TlsMaterial, make_ca_signed, make_self_signed

_service = TlsCertificateService(3.0)


@pytest.fixture
def tls_server(tmp_path: Path) -> Iterator[GitHttpServer]:
    server = GitHttpServer(root=tmp_path / "root", token=None, tls=make_self_signed(tmp_path / "tls"))
    server.start()
    yield server
    server.stop()


def _der(material: TlsMaterial) -> bytes:
    return x509.load_pem_x509_certificate(material.cert_pem.encode()).public_bytes(serialization.Encoding.DER)


async def test__fetch__self_signed_server__describes_the_presented_certificate(tls_server: GitHttpServer) -> None:
    assert tls_server.tls is not None

    certificate = await _service.fetch("127.0.0.1", tls_server.port)

    assert certificate.fingerprint_sha256 == certificate_fingerprint(_der(tls_server.tls))
    assert certificate.self_signed is True
    assert (certificate.subject, certificate.issuer) == ("CN=127.0.0.1", "CN=127.0.0.1")
    assert certificate.not_before < certificate.not_after
    assert certificate.pem == tls_server.tls.cert_pem


async def test__fetch__certificate_of_an_internal_ca__is_not_self_signed(tmp_path: Path) -> None:
    server = GitHttpServer(root=tmp_path / "root", token=None, tls=make_ca_signed(tmp_path / "tls"))
    server.start()
    try:
        certificate = await _service.fetch("127.0.0.1", server.port)
    finally:
        server.stop()

    assert certificate.self_signed is False
    assert certificate.issuer == "CN=Test Internal CA"


def test__fingerprint__has_the_shape_browsers_and_openssl_show() -> None:
    value = certificate_fingerprint(b"der")

    assert value == "SHA256:" + base64.b64encode(hashlib.sha256(b"der").digest()).decode().rstrip("=")
    assert len(value) == len("SHA256:") + 43


async def test__fetch__nobody_listens__is_offline() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    with pytest.raises(GitSyncError) as error:
        await _service.fetch("127.0.0.1", port)

    assert error.value.code is GitErrorCode.offline


async def test__fetch__plain_http_port__is_a_tls_error(tmp_path: Path) -> None:
    server = GitHttpServer(root=tmp_path / "root", token=None)
    server.start()
    try:
        with pytest.raises(GitSyncError) as error:
            await _service.fetch("127.0.0.1", server.port)
    finally:
        server.stop()

    assert error.value.code in {GitErrorCode.tls_error, GitErrorCode.timeout}


def test__normalize_ca_pem__certificate__is_returned_in_canonical_form(tmp_path: Path) -> None:
    material = make_self_signed(tmp_path)

    assert _service.normalize_ca_pem("\n  " + material.cert_pem + "\n\n") == material.cert_pem


def test__normalize_ca_pem__bundle__keeps_every_certificate(tmp_path: Path) -> None:
    first, second = make_self_signed(tmp_path / "a"), make_self_signed(tmp_path / "b")

    result = _service.normalize_ca_pem(first.cert_pem + "text between\n" + second.cert_pem)

    assert result == first.cert_pem + second.cert_pem


def test__normalize_ca_pem__private_key__is_rejected_and_not_echoed(tmp_path: Path) -> None:
    material = make_self_signed(tmp_path)
    pem = material.cert_pem + material.key_file.read_text(encoding="ascii")

    with pytest.raises(GitSyncError) as error:
        _service.normalize_ca_pem(pem)

    assert error.value.code is GitErrorCode.host_settings_invalid
    assert "PRIVATE" not in error.value.detail


@pytest.mark.parametrize(
    "text", ["", "   ", "not a certificate", "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----"]
)
def test__normalize_ca_pem__garbage__is_rejected(text: str) -> None:
    with pytest.raises(GitSyncError) as error:
        _service.normalize_ca_pem(text)

    assert error.value.code is GitErrorCode.host_settings_invalid


def test__normalize_ca_pem__too_many_certificates__is_rejected(tmp_path: Path) -> None:
    material = make_self_signed(tmp_path)

    with pytest.raises(GitSyncError) as error:
        _service.normalize_ca_pem(material.cert_pem * 11)

    assert error.value.code is GitErrorCode.host_settings_invalid
