from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISigningIdentityRepository

logger = structlog.get_logger()


@dataclass
class CreateSelfSignedInput:
    label: str
    subject_cn: str
    validity_days: int = 825  # ~2.25 years; matches max browser/CA limits


@dataclass
class CreateSelfSignedOutput:
    identity: SigningIdentity


class CreateSelfSignedUC:
    """Generates a self-signed RSA certificate + private key in-app.

    Uses only `cryptography` (already a base dependency — no pyHanko needed
    here). The private key is written to data_dir/signing_keys/<id>/key.pem
    and the certificate to .../cert.pem. The identity metadata (without any
    key material) is persisted in signing_identities.json.

    The resulting identity is always marked `trusted=False` because it does
    not chain to any externally-accredited root CA. It is suitable for
    internal verification (adding our own root to a trust store) but not for
    third-party legal validity.
    """

    def __init__(self, repo: ISigningIdentityRepository) -> None:
        self._repo = repo

    async def execute(self, inp: CreateSelfSignedInput) -> CreateSelfSignedOutput:
        if not inp.label.strip():
            raise ValueError(localized_error("label не может быть пустым", "label cannot be empty"))
        if not inp.subject_cn.strip():
            raise ValueError(localized_error("subject_cn не может быть пустым", "subject_cn cannot be empty"))
        if not (1 <= inp.validity_days <= 3650):
            raise ValueError(
                localized_error(
                    "validity_days должен быть от 1 до 3650",
                    "validity_days must be between 1 and 3650",
                )
            )

        identity_id = uuid.uuid4()
        now = datetime.datetime.now(datetime.timezone.utc)
        not_after = now + datetime.timedelta(days=inp.validity_days)

        key_dir = self._repo.key_dir(identity_id)
        _generate_self_signed(inp.subject_cn, not_after, key_dir)

        identity = SigningIdentity(
            id=identity_id,
            label=inp.label.strip(),
            kind=SigningIdentityKind.self_signed,
            subject_cn=inp.subject_cn.strip(),
            not_after=not_after,
            trusted=False,
            created_at=now,
        )
        self._repo.create(identity)
        logger.info("signing_identity: self-signed created", id=str(identity_id), cn=inp.subject_cn)
        return CreateSelfSignedOutput(identity=identity)


def _generate_self_signed(subject_cn: str, not_after: datetime.datetime, key_dir: Path) -> None:  # noqa: PLC0415
    from cryptography import x509  # noqa: PLC0415
    from cryptography.hazmat.primitives import hashes, serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: PLC0415
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID  # noqa: PLC0415

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)])
    now = datetime.datetime.now(datetime.timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(seconds=60))
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    (key_dir / "key.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    (key_dir / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
