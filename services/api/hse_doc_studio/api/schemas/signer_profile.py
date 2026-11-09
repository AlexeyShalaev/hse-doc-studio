"""Профиль подписанта в API: метаданные картинки и данные плашки из открытой части ключа, без самих файлов."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from hse_doc_studio.core.signatures.signer_profile import PublicKeyKind, SignerProfile


class ProfileImageResponse(BaseModel):
    sha256: str
    size: int
    width_px: int | None
    height_px: int | None
    updated_at: datetime


class ProfilePublicKeyResponse(BaseModel):
    kind: PublicKeyKind
    owner: str
    # Серийный номер сертификата или id ключа OpenPGP, как на плашке.
    cert_id: str
    valid_from: str | None
    valid_to: str | None
    # SHA-256 сертификата или отпечаток ключа OpenPGP: с ним сверяется пришедшая подпись.
    signer_id: str
    level: str
    updated_at: datetime


class SignerProfileResponse(BaseModel):
    image: ProfileImageResponse | None
    public_key: ProfilePublicKeyResponse | None


def map_signer_profile(profile: SignerProfile) -> SignerProfileResponse:
    image = profile.image
    key = profile.public_key
    return SignerProfileResponse(
        image=None
        if image is None
        else ProfileImageResponse(
            sha256=image.sha256,
            size=image.size,
            width_px=image.width_px,
            height_px=image.height_px,
            updated_at=image.updated_at,
        ),
        public_key=None
        if key is None
        else ProfilePublicKeyResponse(
            kind=key.kind,
            owner=key.plate.owner,
            cert_id=key.plate.cert_id,
            valid_from=key.plate.valid_from,
            valid_to=key.plate.valid_to,
            signer_id=key.plate.signer_id,
            level=key.plate.level,
            updated_at=key.updated_at,
        ),
    )
