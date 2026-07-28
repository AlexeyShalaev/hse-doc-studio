from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

import structlog

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISigningIdentityRepository

logger = structlog.get_logger()


@dataclass
class ImportPkcs12Input:
    label: str
    p12_bytes: bytes
    passphrase: bytes | None = None


@dataclass
class ImportPkcs12Output:
    identity: SigningIdentity


class ImportPkcs12UC:
    """Import a PKCS#12 (.p12 / .pfx) bundle as a signing identity.

    Extracts the end-entity certificate, saves key + cert as PEM files in
    data_dir/signing_keys/<id>/. The identity is marked `trusted=True` only
    when the certificate chains to an externally-recognised root (which we
    cannot verify offline without the full chain — so we set trusted=False and
    let the UI show an informational note; the user knows whether their cert
    came from a real УЦ).
    """

    def __init__(self, repo: ISigningIdentityRepository) -> None:
        self._repo = repo

    async def execute(self, inp: ImportPkcs12Input) -> ImportPkcs12Output:
        if not inp.label.strip():
            raise ValueError(localized_error("label не может быть пустым", "label cannot be empty"))
        if not inp.p12_bytes:
            raise ValueError(localized_error("p12_bytes не может быть пустым", "p12_bytes cannot be empty"))

        identity_id = uuid.uuid4()
        now = datetime.datetime.now(datetime.timezone.utc)

        key_dir = self._repo.key_dir(identity_id)
        subject_cn, not_after = _extract_and_save(inp.p12_bytes, inp.passphrase, key_dir)

        identity = SigningIdentity(
            id=identity_id,
            label=inp.label.strip(),
            kind=SigningIdentityKind.pkcs12,
            subject_cn=subject_cn,
            not_after=not_after,
            trusted=False,  # set to True manually if chain is verified
            created_at=now,
        )
        self._repo.create(identity)
        logger.info("signing_identity: pkcs12 imported", id=str(identity_id), cn=subject_cn)
        return ImportPkcs12Output(identity=identity)


def _extract_and_save(  # noqa: PLC0415
    p12_bytes: bytes, passphrase: bytes | None, key_dir: object
) -> tuple[str, datetime.datetime]:
    from cryptography.hazmat.primitives import serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.serialization import pkcs12  # noqa: PLC0415
    from cryptography.x509.oid import NameOID  # noqa: PLC0415

    private_key, cert, _ = pkcs12.load_key_and_certificates(p12_bytes, passphrase)
    if cert is None:
        raise ValueError(
            localized_error(
                "PKCS#12-контейнер не содержит сертификата",
                "PKCS#12 bundle contains no certificate",
            )
        )
    if private_key is None:
        raise ValueError(
            localized_error(
                "PKCS#12-контейнер не содержит закрытого ключа",
                "PKCS#12 bundle contains no private key",
            )
        )

    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    cn_value = cn_attrs[0].value if cn_attrs else "Unknown"
    subject_cn = cn_value if isinstance(cn_value, str) else cn_value.decode("utf-8", errors="replace")
    not_after = cert.not_valid_after_utc

    from pathlib import Path  # noqa: PLC0415

    key_dir_path = Path(str(key_dir))
    key_dir_path.mkdir(parents=True, exist_ok=True)

    (key_dir_path / "key.pem").write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (key_dir_path / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return subject_cn, not_after
