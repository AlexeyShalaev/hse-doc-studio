"""Свой профиль подписанта: картинка подписи и открытая часть ключа (docs/design/signing-route.md, срез R10).

Профиль меняет и видит только его владелец: сценарии берут id из актора запроса, чужой id сюда не передать. Каждое
изменение пишется в аудит подписей без содержимого файлов.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import structlog

from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.signatures.ports import ISignatureAudit
from hse_doc_studio.core.signatures.signer_profile import (
    MAX_PROFILE_IMAGE_BYTES,
    IPublicKeyReader,
    ISignerProfileRepository,
    ProfileImage,
    ProfilePublicKey,
    SignerProfile,
    png_size,
)

logger = structlog.get_logger()


def owner_id(actor: Actor) -> str:
    """Id владельца профиля: только вошедший человек, гость по ссылке профиля не имеет."""
    if actor.kind is not ActorKind.user or not actor.id:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor.id


class GetSignerProfileUC:
    def __init__(self, repo: ISignerProfileRepository) -> None:
        self._repo = repo

    async def execute(self, actor: Actor) -> SignerProfile:
        return await self._repo.get(owner_id(actor))


class ReadProfileImageUC:
    def __init__(self, repo: ISignerProfileRepository) -> None:
        self._repo = repo

    async def execute(self, actor: Actor) -> bytes | None:
        return await self._repo.read_image(owner_id(actor))


class SaveProfileImageUC:
    """Картинка подписи для любых проектов: PNG, нарисованный или очищенный от фона в редакторе."""

    def __init__(self, repo: ISignerProfileRepository, audit: ISignatureAudit) -> None:
        self._repo = repo
        self._audit = audit

    async def execute(self, actor: Actor, png: bytes) -> SignerProfile:
        user_id = owner_id(actor)
        if not png:
            raise ValueError(localized_error("Загружен пустой файл", "Empty file upload"))
        if len(png) > MAX_PROFILE_IMAGE_BYTES:
            raise ValueError(
                localized_error(
                    "Картинка подписи больше 2 МБ: уменьшите её или удалите фон в редакторе",
                    "The signature image is larger than 2 MB: shrink it or remove the background in the editor",
                )
            )
        dims = png_size(png)
        if dims is None:
            raise ValueError(localized_error("Загруженный файл не является PNG", "Uploaded file is not a PNG"))
        image = ProfileImage(
            sha256=hashlib.sha256(png).hexdigest(),
            size=len(png),
            width_px=dims[0],
            height_px=dims[1],
            updated_at=datetime.now(UTC),
        )
        await self._repo.save_image(user_id, png, image)
        await self._audit.record("signature.profile_image", project_id=None, details={"sha256": image.sha256})
        logger.info("signer profile image saved", user_id=user_id, size=image.size)
        return await self._repo.get(user_id)


class ClearProfileImageUC:
    def __init__(self, repo: ISignerProfileRepository, audit: ISignatureAudit) -> None:
        self._repo = repo
        self._audit = audit

    async def execute(self, actor: Actor) -> SignerProfile:
        user_id = owner_id(actor)
        if await self._repo.clear_image(user_id):
            await self._audit.record("signature.profile_image_cleared", project_id=None, details={})
        return await self._repo.get(user_id)


class SaveProfilePublicKeyUC:
    """Сертификат X.509 или открытый ключ OpenPGP для плашки; файл с закрытым ключом отвергается целиком."""

    def __init__(self, repo: ISignerProfileRepository, reader: IPublicKeyReader, audit: ISignatureAudit) -> None:
        self._repo = repo
        self._reader = reader
        self._audit = audit

    async def execute(self, actor: Actor, blob: bytes) -> SignerProfile:
        user_id = owner_id(actor)
        parsed = await self._reader.read(blob)
        key = ProfilePublicKey(kind=parsed.kind, data=parsed.data, plate=parsed.plate, updated_at=datetime.now(UTC))
        await self._repo.save_public_key(user_id, key)
        await self._audit.record(
            "signature.profile_key",
            project_id=None,
            details={"kind": key.kind.value, "signer_id": key.plate.signer_id},
        )
        logger.info("signer profile public key saved", user_id=user_id, kind=key.kind.value)
        return await self._repo.get(user_id)


class ClearProfilePublicKeyUC:
    def __init__(self, repo: ISignerProfileRepository, audit: ISignatureAudit) -> None:
        self._repo = repo
        self._audit = audit

    async def execute(self, actor: Actor) -> SignerProfile:
        user_id = owner_id(actor)
        if await self._repo.clear_public_key(user_id):
            await self._audit.record("signature.profile_key_cleared", project_id=None, details={})
        return await self._repo.get(user_id)
