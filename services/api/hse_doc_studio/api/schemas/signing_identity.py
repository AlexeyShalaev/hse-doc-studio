from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import SigningIdentityKind


class SigningIdentityResponse(BaseModel):
    id: UUID
    label: str
    kind: SigningIdentityKind
    subject_cn: str
    not_after: datetime
    trusted: bool
    created_at: datetime


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
    )
