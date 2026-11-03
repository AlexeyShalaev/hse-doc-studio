"""InMemory-реализация репозитория passkey: те же правила, что у Postgres."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime

from hse_doc_studio.core.identity.passkeys import Passkey, PasskeyFailure, PasskeyVerificationError


class InMemoryPasskeyRepository:
    def __init__(self) -> None:
        self._items: dict[str, Passkey] = {}

    async def add(self, passkey: Passkey) -> None:
        if any(p.credential_id == passkey.credential_id for p in self._items.values()):
            raise PasskeyVerificationError(PasskeyFailure.duplicate)
        self._items[passkey.id] = passkey

    async def get_by_credential_id(self, credential_id: str) -> Passkey | None:
        return next((p for p in self._items.values() if p.credential_id == credential_id), None)

    async def list_for_user(self, user_id: str) -> list[Passkey]:
        found = [p for p in self._items.values() if p.user_id == user_id]
        return sorted(found, key=lambda p: (p.created_at, p.id))

    async def count_for_user(self, user_id: str) -> int:
        return sum(1 for p in self._items.values() if p.user_id == user_id)

    async def rename(self, user_id: str, passkey_id: str, name: str) -> Passkey | None:
        found = self._items.get(passkey_id)
        if found is None or found.user_id != user_id:
            return None
        self._items[passkey_id] = replace(found, name=name)
        return self._items[passkey_id]

    async def delete(self, user_id: str, passkey_id: str) -> bool:
        found = self._items.get(passkey_id)
        if found is None or found.user_id != user_id:
            return False
        del self._items[passkey_id]
        return True

    async def delete_for_user(self, user_id: str) -> int:
        doomed = [k for k, p in self._items.items() if p.user_id == user_id]
        for key in doomed:
            del self._items[key]
        return len(doomed)

    async def record_use(self, passkey_id: str, *, sign_count: int, backed_up: bool, now: datetime) -> None:
        if passkey_id in self._items:
            self._items[passkey_id] = replace(
                self._items[passkey_id], sign_count=sign_count, backed_up=backed_up, last_used_at=now
            )

    async def count_by_rp_id(self) -> dict[str, int]:
        return dict(Counter(p.rp_id for p in self._items.values()))
