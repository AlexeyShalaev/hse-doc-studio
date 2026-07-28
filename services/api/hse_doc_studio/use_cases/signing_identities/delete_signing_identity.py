from __future__ import annotations

import shutil
from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISigningIdentityRepository

logger = structlog.get_logger()


@dataclass
class DeleteSigningIdentityInput:
    identity_id: UUID


class DeleteSigningIdentityUC:
    def __init__(self, repo: ISigningIdentityRepository) -> None:
        self._repo = repo

    async def execute(self, inp: DeleteSigningIdentityInput) -> None:
        identity = self._repo.get(inp.identity_id)
        if identity is None:
            raise NotFoundError(
                localized_error(
                    f"Учётная запись подписи {inp.identity_id} не найдена",
                    f"Signing identity {inp.identity_id} not found",
                )
            )

        key_dir = self._repo.key_dir(inp.identity_id)
        self._repo.delete(inp.identity_id)

        # Remove key material AFTER the metadata is gone from the JSON so a
        # partial failure (e.g. locked file on Windows) never leaves a dangling
        # entry with broken key references.
        if key_dir.exists():
            try:
                shutil.rmtree(key_dir)
            except OSError as exc:
                logger.warning("signing_identity: could not remove key dir", exc=str(exc), dir=str(key_dir))

        logger.info("signing_identity: deleted", id=str(inp.identity_id))
