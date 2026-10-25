"""Downloads missing issuer certificates named in a certificate's AIA extension.

Only on an explicit user action: the Studio otherwise makes no network calls while checking a
signature. Downloaded certificates go to a cache and are used to *build* the chain; they are
never trusted by themselves.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx
import structlog
from asn1crypto import x509

from hse_doc_studio.infra.signatures.cms_inspector import embedded_certificates, issuer_urls

logger = structlog.get_logger()

_MAX_DEPTH = 5
_MAX_BYTES = 256 * 1024
_TIMEOUT = 10.0


def _is_public_http(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


class ChainFetcher:
    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir

    @property
    def directory(self) -> Path:
        return self._dir

    def load(self, fingerprint: str) -> bytes | None:
        path = self._dir / f"{Path(fingerprint).name}.cer"
        return path.read_bytes() if path.is_file() else None

    def complete(self, sig_bytes: bytes) -> list[str]:
        """Follow AIA links from the certificates in the signature; returns SHA-256s of what was fetched."""
        certs = embedded_certificates(sig_bytes)
        known = {c.subject.dump() for c in certs}
        queue = list(certs)
        fetched: list[str] = []
        for _ in range(_MAX_DEPTH):
            if not queue:
                break
            cert = queue.pop(0)
            if cert.subject.dump() == cert.issuer.dump() or cert.issuer.dump() in known:
                continue
            issuer = self._fetch_issuer(cert)
            if issuer is None:
                continue
            known.add(issuer.subject.dump())
            queue.append(issuer)
            fetched.append(hashlib.sha256(issuer.dump()).hexdigest())
        return fetched

    def _fetch_issuer(self, cert: x509.Certificate) -> x509.Certificate | None:
        for url in issuer_urls(cert):
            if not _is_public_http(url):
                logger.warning("chain_fetcher: skipping non-public url", url=url)
                continue
            try:
                resp = httpx.get(url, timeout=_TIMEOUT, follow_redirects=False)
                resp.raise_for_status()
                if len(resp.content) > _MAX_BYTES:
                    continue
                blob = resp.content
                if blob.lstrip().startswith(b"-----BEGIN"):
                    from asn1crypto import pem  # noqa: PLC0415

                    blob = pem.unarmor(blob)[2]
                issuer = x509.Certificate.load(blob)
            except Exception as exc:
                logger.warning("chain_fetcher: download failed", url=url, exc=str(exc))
                continue
            if issuer.subject.dump() != cert.issuer.dump():
                continue
            self._dir.mkdir(parents=True, exist_ok=True)
            (self._dir / f"{hashlib.sha256(issuer.dump()).hexdigest()}.cer").write_bytes(issuer.dump())
            return issuer
        return None
