from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISigningIdentityRepository
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring

logger = structlog.get_logger()


@dataclass
class DeleteSigningIdentityInput:
    identity_id: UUID


class DeleteSigningIdentityUC:
    def __init__(self, repo: ISigningIdentityRepository, keyring: GpgKeyring | None = None) -> None:
        self._repo = repo
        self._keyring = keyring

    async def execute(self, inp: DeleteSigningIdentityInput) -> None:
        identity = await self._repo.get(inp.identity_id)
        if identity is None:
            raise NotFoundError(
                localized_error(
                    f"Учётная запись подписи {inp.identity_id} не найдена",
                    f"Signing identity {inp.identity_id} not found",
                )
            )

        await self._repo.delete(inp.identity_id)
        if identity.kind is SigningIdentityKind.openpgp and identity.fingerprint and self._keyring is not None:
            self._keyring.delete(identity.fingerprint)

        logger.info("signing_identity: deleted", id=str(inp.identity_id))
