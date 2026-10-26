"""Сертификаты серверов: чтение предъявленного сертификата и проверка PEM, который вставил человек.

Сертификат сервера читается рукопожатием TLS без проверки цепочки: Студия только показывает, что предъявлено,
и сама ничего этим соединением не отправляет. Доверие появляется отдельным шагом, после подтверждения человеком.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from hse_doc_studio.core.git_sync.entities import ServerCertificate
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.host_settings import DEFAULT_HTTPS_PORT
from hse_doc_studio.core.i18n import localized_error

_MAX_CA_PEM_BYTES = 128 * 1024
_MAX_CA_CERTIFICATES = 10
_PRIVATE_KEY_MARK = "PRIVATE KEY"


def certificate_fingerprint(der: bytes) -> str:
    """`SHA256:...` по DER-кодировке сертификата: так же показывают отпечатки браузеры и openssl."""
    return "SHA256:" + base64.b64encode(hashlib.sha256(der).digest()).decode().rstrip("=")


def describe_certificate(cert: x509.Certificate) -> ServerCertificate:
    der = cert.public_bytes(serialization.Encoding.DER)
    return ServerCertificate(
        fingerprint_sha256=certificate_fingerprint(der),
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        self_signed=cert.subject == cert.issuer,
        pem=cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
    )


def _invalid_ca() -> GitSyncError:
    return GitSyncError(
        GitErrorCode.host_settings_invalid,
        localized_error(
            "Нужен сертификат в формате PEM (-----BEGIN CERTIFICATE-----), без закрытого ключа",
            "A PEM certificate (-----BEGIN CERTIFICATE-----) is required, without a private key",
        ),
    )


class TlsCertificateService:
    def __init__(self, timeout_s: float) -> None:
        self._timeout_s = timeout_s

    def normalize_ca_pem(self, pem: str) -> str:
        raw = pem.strip().encode("utf-8", errors="replace")
        if not raw or len(raw) > _MAX_CA_PEM_BYTES or _PRIVATE_KEY_MARK.encode() in raw:
            raise _invalid_ca()
        try:
            certificates = x509.load_pem_x509_certificates(raw)
        except ValueError:
            raise _invalid_ca() from None
        if not certificates or len(certificates) > _MAX_CA_CERTIFICATES:
            raise _invalid_ca()
        return "".join(cert.public_bytes(serialization.Encoding.PEM).decode("ascii") for cert in certificates)

    async def fetch(self, host: str, port: int | None) -> ServerCertificate:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        writer: asyncio.StreamWriter | None = None
        try:
            opened = await asyncio.wait_for(
                asyncio.open_connection(host, port or DEFAULT_HTTPS_PORT, ssl=context, server_hostname=host),
                timeout=self._timeout_s,
            )
            writer = opened[1]
            ssl_object = writer.get_extra_info("ssl_object")
            der = ssl_object.getpeercert(binary_form=True) if ssl_object is not None else None
        except TimeoutError:
            raise git_error(GitErrorCode.timeout) from None
        except ssl.SSLError:
            raise git_error(GitErrorCode.tls_error) from None
        except OSError:
            raise git_error(GitErrorCode.offline) from None
        finally:
            if writer is not None:
                writer.close()
        if not der:
            raise git_error(GitErrorCode.tls_error)
        return describe_certificate(x509.load_der_x509_certificate(der))
