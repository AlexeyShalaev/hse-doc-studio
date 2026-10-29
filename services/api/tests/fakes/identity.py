"""InMemory-реализации портов identity: те же правила, что у Postgres, без БД."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import replace

from hse_doc_studio.core.identity.entities import User, UserIdentity, UserListing, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email


class InMemoryIdentityStore:
    """Общее состояние пользователей и паролей: админ создаётся вместе с хешем, как в одной транзакции."""

    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.identities: dict[tuple[str, str], UserIdentity] = {}
        self.hashes: dict[str, str] = {}


class InMemoryUserRepository:
    def __init__(self, store: InMemoryIdentityStore | None = None) -> None:
        self._store = store or InMemoryIdentityStore()

    async def get(self, user_id: str) -> User | None:
        return self._store.users.get(user_id)

    async def get_for_update(self, user_id: str) -> User | None:
        return self._store.users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        key = normalize_email(email)
        return next((u for u in self._store.users.values() if u.email_normalized == key), None)

    async def add(self, user: User) -> None:
        if await self.get_by_email(user.email_normalized) is not None:
            raise IdentityError(IdentityErrorCode.email_taken)
        self._store.users[user.id] = user

    async def update(self, user: User) -> None:
        if user.id not in self._store.users:
            raise IdentityError(IdentityErrorCode.forbidden)
        other = await self.get_by_email(user.email_normalized)
        if other is not None and other.id != user.id:
            raise IdentityError(IdentityErrorCode.email_taken)
        self._store.users[user.id] = user

    async def count(self) -> int:
        return len(self._store.users)

    async def lock_active_admins(self) -> int:
        return sum(1 for u in self._store.users.values() if u.is_instance_admin and u.can_sign_in)

    async def get_by_identity(self, provider: str, subject: str) -> User | None:
        identity = self._store.identities.get((provider, subject))
        return self._store.users.get(identity.user_id) if identity else None

    async def add_identity(self, identity: UserIdentity) -> None:
        key = (identity.provider, identity.subject)
        if key in self._store.identities:
            raise IdentityError(IdentityErrorCode.forbidden)
        self._store.identities[key] = identity

    async def delete_identity(self, user_id: str, provider: str) -> int:
        keys = [k for k, i in self._store.identities.items() if i.user_id == user_id and i.provider == provider]
        for key in keys:
            del self._store.identities[key]
        return len(keys)

    async def list_identities(self, user_id: str) -> list[UserIdentity]:
        found = [i for i in self._store.identities.values() if i.user_id == user_id]
        return sorted(found, key=lambda i: (i.provider, i.subject))


class InMemoryUserDirectory:
    """Список пользователей над общим хранилищем; число проектов задаёт тест через `project_counts`."""

    def __init__(self, store: InMemoryIdentityStore, project_counts: Mapping[str, int] | None = None) -> None:
        self._store = store
        self.project_counts: dict[str, int] = dict(project_counts or {})

    def _listing(self, user: User) -> UserListing:
        return UserListing(user, self.project_counts.get(user.id, 0))

    async def get(self, user_id: str) -> UserListing | None:
        user = self._store.users.get(user_id)
        return self._listing(user) if user else None

    async def search(
        self, *, q: str | None, status: UserStatus | None, limit: int, offset: int
    ) -> tuple[list[UserListing], int]:
        needle = (q or "").strip().lower()
        found = [
            u
            for u in self._store.users.values()
            if (status is None or u.status is status)
            and (not needle or needle in u.name.lower() + " " + u.email_normalized)
        ]
        found.sort(key=lambda u: (-u.created_at.timestamp(), u.id))
        return [self._listing(u) for u in found[offset : offset + limit]], len(found)


class InMemoryCredentialRepository:
    def __init__(self, store: InMemoryIdentityStore | None = None) -> None:
        self._store = store or InMemoryIdentityStore()

    async def get_hash(self, user_id: str) -> str | None:
        return self._store.hashes.get(user_id)

    async def set_hash(self, user_id: str, password_hash: str) -> None:
        self._store.hashes[user_id] = password_hash


class InMemoryFirstAdminRepository:
    """Между проверкой и записью нет await, поэтому в одном цикле событий вызов атомарен."""

    def __init__(self, store: InMemoryIdentityStore | None = None) -> None:
        self._store = store or InMemoryIdentityStore()

    async def create_first_admin(self, user: User, password_hash: str) -> None:
        if any(u.is_instance_admin for u in self._store.users.values()):
            raise IdentityError(IdentityErrorCode.setup_already_done)
        await InMemoryUserRepository(self._store).add(replace(user))
        self._store.hashes[user.id] = password_hash


class InMemoryInstanceSettingsRepository:
    def __init__(self) -> None:
        self._values: dict[str, object] = {}
        self._secrets: dict[str, str] = {}

    async def get_all(self) -> Mapping[str, object]:
        return copy.deepcopy(self._values)

    async def set(self, key: str, value: object, *, source: str) -> None:
        self._values[key] = copy.deepcopy(value)
        self._secrets.pop(key, None)

    async def delete(self, key: str) -> None:
        self._values.pop(key, None)
        self._secrets.pop(key, None)

    async def get_secret(self, key: str) -> str | None:
        return self._secrets.get(key)

    async def set_secret(self, key: str, token: str, *, source: str) -> None:
        self._values[key] = True
        self._secrets[key] = token
