from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.infra.signatures.openpgp import GpgKey


class SigningIdentityResponse(BaseModel):
    id: UUID
    label: str
    kind: SigningIdentityKind
    subject_cn: str
    not_after: datetime
    trusted: bool
    created_at: datetime
    fingerprint: str | None = None
    protected: bool = False


class OpenPgpKeyResponse(BaseModel):
    fingerprint: str
    key_id: str
    uids: list[str]
    has_secret: bool
    algo: str
    created: datetime | None
    expires: datetime | None


class OpenPgpKeysResponse(BaseModel):
    available: bool
    gpg_version: str | None
    keys: list[OpenPgpKeyResponse]


class GenerateOpenPgpKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(default="", max_length=200)
    label: str = Field(default="", max_length=120)
    passphrase: str = Field(default="", max_length=500)


class ImportOpenPgpKeyResponse(BaseModel):
    identities: list[SigningIdentityResponse]
    public_keys: list[OpenPgpKeyResponse]


class TrustedRootResponse(BaseModel):
    fingerprint: str
    subject: str
    not_before: datetime
    not_after: datetime


class CreateSelfSignedRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    subject_cn: str = Field(min_length=1, max_length=200)
    validity_days: int = Field(default=825, ge=1, le=3650)


class ImportPkcs12Request(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    # p12 bytes are uploaded as multipart; passphrase as optional form field.


def map_identity(identity: SigningIdentity) -> SigningIdentityResponse:
    return SigningIdentityResponse(
        id=identity.id,
        label=identity.label,
        kind=identity.kind,
        subject_cn=identity.subject_cn,
        not_after=identity.not_after,
        trusted=identity.trusted,
        created_at=identity.created_at,
        fingerprint=identity.fingerprint,
        protected=identity.protected,
    )


def map_openpgp_key(key: GpgKey) -> OpenPgpKeyResponse:
    return OpenPgpKeyResponse(
        fingerprint=key.fingerprint,
        key_id=key.key_id,
        uids=key.uids,
        has_secret=key.has_secret,
        algo=key.algo,
        created=key.created,
        expires=key.expires,
    )
