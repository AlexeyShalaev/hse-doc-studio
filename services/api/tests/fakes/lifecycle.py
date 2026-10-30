"""InMemory-реализация жизненного цикла данных человека над общим хранилищем identity."""

from __future__ import annotations

from collections.abc import Mapping

from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.lifecycle import DeletionBlockers, ErasureReport

from tests.fakes.identity import InMemoryIdentityStore


class InMemoryUserLifecycle:
    def __init__(self, store: InMemoryIdentityStore) -> None:
        self._store = store
        self.owned_projects: dict[str, int] = {}
        self.sole_orgs: dict[str, int] = {}
        self.erased: list[tuple[str, str]] = []

    async def blockers(self, user_id: str) -> DeletionBlockers:
        return DeletionBlockers(self.owned_projects.get(user_id, 0), self.sole_orgs.get(user_id, 0))

    async def erase(self, user_id: str, pseudonym: str) -> ErasureReport:
        if user_id not in self._store.users:
            raise IdentityError(IdentityErrorCode.not_found)
        del self._store.users[user_id]
        self._store.hashes.pop(user_id, None)
        for key in [k for k, i in self._store.identities.items() if i.user_id == user_id]:
            del self._store.identities[key]
        self.erased.append((user_id, pseudonym))
        return ErasureReport(audit_anonymized=0, api_tokens=0, sessions=0, settings=0)

    async def export(self, user_id: str) -> Mapping[str, object]:
        user = self._store.users[user_id]
        return {"profile": {"id": user.id, "email": user.email}}
