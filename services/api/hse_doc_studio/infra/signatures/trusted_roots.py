from __future__ import annotations

import contextlib
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import structlog
from asn1crypto import pem, x509

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.infra.signatures.cms_inspector import subject_display

logger = structlog.get_logger()


@dataclass(frozen=True)
class TrustedRoot:
    fingerprint: str  # SHA-256 of the DER certificate; also the file name stem
    subject: str
    not_before: datetime
    not_after: datetime


class TrustedRootStore:
    """Root / intermediate certificates the user trusts for CMS signatures (data_dir/trusted_roots).

    Not a trust decision by the Studio: a certificate lands here only because the
    user put it here, e.g. the Минцифры root downloaded from the official site.
    """

    def __init__(self, directory: Path) -> None:
        self._dir = directory

    @property
    def directory(self) -> Path:
        return self._dir

    def list_all(self) -> list[TrustedRoot]:
        if not self._dir.is_dir():
            return []
        roots: list[TrustedRoot] = []
        for path in sorted(self._dir.glob("*.cer")):
            with contextlib.suppress(Exception):
                roots.append(_describe(path.read_bytes(), path.stem))
        return roots

    def add(self, blob: bytes) -> TrustedRoot:
        der = pem.unarmor(blob)[2] if pem.detect(blob) else blob
        try:
            x509.Certificate.load(der)["tbs_certificate"].native  # noqa: B018
        except Exception as exc:
            raise ValueError(
                localized_error(
                    "Файл не похож на сертификат X.509 (.cer / .crt / .pem)",
                    "The file does not look like an X.509 certificate (.cer / .crt / .pem)",
                )
            ) from exc
        fingerprint = hashlib.sha256(der).hexdigest()
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / f"{fingerprint}.cer").write_bytes(der)
        return _describe(der, fingerprint)

    def delete(self, fingerprint: str) -> None:
        path = self._dir / f"{Path(fingerprint).name}.cer"
        if not path.is_file():
            raise NotFoundError(localized_error("Сертификат не найден", "Certificate not found"))
        path.unlink()


def _describe(der: bytes, fingerprint: str) -> TrustedRoot:
    cert = x509.Certificate.load(der)
    validity = cert["tbs_certificate"]["validity"]
    return TrustedRoot(
        fingerprint=fingerprint,
        subject=subject_display(cert),
        not_before=validity["not_before"].native,
        not_after=validity["not_after"].native,
    )
