"""Сертификаты для тестов TLS: самоподписанный и выданный собственным центром, без сети и без openssl."""

from __future__ import annotations

import datetime
import ipaddress
import ssl
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

_DAY = datetime.timedelta(days=1)


@dataclass(frozen=True)
class TlsMaterial:
    """Сертификат сервера (`cert_pem`), его ключ и, если сертификат выдан центром, сам центр (`ca_pem`)."""

    cert_pem: str
    cert_file: Path
    key_file: Path
    ca_pem: str | None = None

    def server_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(self.cert_file), str(self.key_file))
        return context


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _pem(cert: x509.Certificate) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _leaf(
    key: ec.EllipticCurvePrivateKey, issuer: x509.Name, signer: ec.EllipticCurvePrivateKey, serial: int
) -> x509.Certificate:
    now = datetime.datetime.now(datetime.timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(_name("127.0.0.1"))
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now - _DAY)
        .not_valid_after(now + 30 * _DAY)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(signer, hashes.SHA256())
    )


def _write(directory: Path, name: str, cert: x509.Certificate, key: ec.EllipticCurvePrivateKey) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    cert_file, key_file = directory / f"{name}.crt", directory / f"{name}.key"
    cert_file.write_text(_pem(cert), encoding="ascii")
    key_file.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_file, key_file


def make_self_signed(directory: Path, name: str = "self") -> TlsMaterial:
    """Сертификат для 127.0.0.1 и localhost, подписанный своим же ключом."""
    key = ec.generate_private_key(ec.SECP256R1())
    cert = _leaf(key, _name("127.0.0.1"), key, serial=1)
    cert_file, key_file = _write(directory, name, cert, key)
    return TlsMaterial(_pem(cert), cert_file, key_file)


def make_ca_signed(directory: Path, name: str = "signed") -> TlsMaterial:
    """Сертификат сервера, выданный внутренним центром «Test Internal CA», которого нет ни в одном системном списке."""
    ca_key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    ca = (
        x509.CertificateBuilder()
        .subject_name(_name("Test Internal CA"))
        .issuer_name(_name("Test Internal CA"))
        .public_key(ca_key.public_key())
        .serial_number(100)
        .not_valid_before(now - _DAY)
        .not_valid_after(now + 30 * _DAY)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    key = ec.generate_private_key(ec.SECP256R1())
    cert = _leaf(key, ca.subject, ca_key, serial=2)
    cert_file, key_file = _write(directory, name, cert, key)
    return TlsMaterial(_pem(cert), cert_file, key_file, ca_pem=_pem(ca))
