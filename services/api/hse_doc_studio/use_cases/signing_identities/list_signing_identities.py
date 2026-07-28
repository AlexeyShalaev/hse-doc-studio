from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.repositories import ISigningIdentityRepository


@dataclass
class ListSigningIdentitiesOutput:
    identities: list[SigningIdentity]


class ListSigningIdentitiesUC:
    def __init__(self, repo: ISigningIdentityRepository) -> None:
        self._repo = repo

    async def execute(self) -> ListSigningIdentitiesOutput:
        return ListSigningIdentitiesOutput(identities=self._repo.list_all())
