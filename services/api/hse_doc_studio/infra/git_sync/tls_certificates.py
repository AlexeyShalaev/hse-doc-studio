"""Сертификаты серверов: чтение предъявленного сертификата и проверка PEM, который вставил человек.

Сертификат сервера читается рукопожатием TLS без проверки цепочки: Студия только показывает, что предъявлено,
и сама ничего этим соединением не отправляет. Доверие появляется отдельным шагом, после подтверждения человеком.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ssl
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlsplit

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
_MAX_PROXY_REPLY_BYTES = 16 * 1024
_HTTP_OK = range(200, 300)
# Коды openssl X509_V_ERR_*, при которых сертификат не принят из-за незнакомого центра выдачи.
UNTRUSTED_VERIFY_CODES = frozenset({18, 19, 20, 21})


def verifying_ssl_context(ca_file: Path | None) -> ssl.SSLContext:
    """Проверка как у git (curl): внутренние центры часто выдают сертификаты без идентификаторов ключа, а строгий
    режим Python их отвергает; git при этом работает, и проверка не должна быть строже него."""
    context = ssl.create_default_context(cafile=str(ca_file)) if ca_file is not None else ssl.create_default_context()
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


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
            writer = await asyncio.wait_for(
                self._open(host, port or DEFAULT_HTTPS_PORT, context), timeout=self._timeout_s
            )
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

    async def issuer_is_untrusted(self, host: str, port: int | None, ca_file: Path | None) -> bool:
        """Сервер предъявил сертификат, цепочка которого не сходится с доверенными центрами (система и `ca_file`).

        Нужен там, где git не называет причину отказа (libcurl-gnutls): по ответу «проверка не прошла» нельзя
        отличить неизвестный центр от истёкшего срока или чужого имени, а доверять центру можно предложить только
        в первом случае.
        Любой другой исход (сеть, срок, имя, успех) даёт False: решает тот отказ, который назвал git.
        """
        writer: asyncio.StreamWriter | None = None
        try:
            writer = await asyncio.wait_for(
                self._open(host, port or DEFAULT_HTTPS_PORT, verifying_ssl_context(ca_file)), timeout=self._timeout_s
            )
        except ssl.SSLCertVerificationError as exc:
            return exc.verify_code in UNTRUSTED_VERIFY_CODES
        except (TimeoutError, ssl.SSLError, OSError):
            return False
        finally:
            if writer is not None:
                writer.close()
        return False

    async def _open(self, host: str, port: int, context: ssl.SSLContext) -> asyncio.StreamWriter:
        """Соединение с сервером, как его открыл бы git: напрямую или через прокси из окружения (CONNECT)."""
        proxy = _proxy_for(host)
        if proxy is None:
            _, writer = await asyncio.open_connection(host, port, ssl=context, server_hostname=host)
            return writer
        reader, writer = await asyncio.open_connection(proxy.host, proxy.port)
        try:
            await _connect_through(reader, writer, host, port, proxy.authorization)
            await writer.start_tls(context, server_hostname=host)
        except BaseException:
            writer.close()
            raise
        return writer


class _Proxy:
    def __init__(self, host: str, port: int, authorization: str | None) -> None:
        self.host = host
        self.port = port
        self.authorization = authorization


def _proxy_for(host: str) -> _Proxy | None:
    """Прокси для https-адреса по тем же переменным окружения, что получает git; None, если соединяться напрямую.

    Поддерживается обычный http-прокси (CONNECT). Адрес из NO_PROXY и прокси другого вида (socks, https) идут
    напрямую: ради сертификата это усложнение не стоит.
    """
    proxies = urllib.request.getproxies_environment()
    raw = proxies.get("https") or proxies.get("all")
    if not raw or _bypassed(host, proxies.get("no", "")):
        return None
    parts = urlsplit(raw if "://" in raw else f"http://{raw}")
    if parts.scheme != "http" or not parts.hostname:
        return None
    authorization = None
    if parts.username is not None:
        credentials = f"{unquote(parts.username)}:{unquote(parts.password or '')}"
        authorization = "Basic " + base64.b64encode(credentials.encode()).decode()
    return _Proxy(parts.hostname, parts.port or 80, authorization)


def _bypassed(host: str, no_proxy: str) -> bool:
    """Адрес из NO_PROXY: `*`, имя хоста или суффикс домена (`.corp.example`, `corp.example`) без учёта регистра."""
    name = host.lower().rstrip(".")
    for item in (part.strip().lower() for part in no_proxy.split(",")):
        suffix = item.split(":", 1)[0].lstrip("*").lstrip(".")
        if item == "*" or (suffix and (name == suffix or name.endswith(f".{suffix}"))):
            return True
    return False


async def _connect_through(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, host: str, port: int, authorization: str | None
) -> None:
    target = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    lines = [f"CONNECT {target} HTTP/1.1", f"Host: {target}"]
    if authorization is not None:
        lines.append(f"Proxy-Authorization: {authorization}")
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
    await writer.drain()
    reply = await reader.readuntil(b"\r\n\r\n")
    if len(reply) > _MAX_PROXY_REPLY_BYTES:
        raise ConnectionError("proxy reply is too long")
    status = reply.split(b"\r\n", 1)[0].split()
    if len(status) < 2 or not status[1].isdigit() or int(status[1]) not in _HTTP_OK:  # noqa: PLR2004
        raise ConnectionError("proxy refused the tunnel")
