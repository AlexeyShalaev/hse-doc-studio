"""Порты identity. Репозитории APP-scope: сессию БД берут на вызов, а многотабличные записи
объединяет ambient `IUnitOfWork`. SQL-реализации лежат в infra, в тестах им соответствуют фейки."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Protocol

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import (
    ActorCredentials,
    ApiToken,
    AuditEntry,
    AuthToken,
    AuthTokenKind,
    LoginAttempt,
    MailOutboxEntry,
    OidcProvider,
    RegistrationInvite,
    Session,
    User,
    UserIdentity,
    UserListing,
    UserStatus,
)


class IUserRepository(Protocol):
    async def get(self, user_id: str) -> User | None: ...
    async def get_by_email(self, email: str) -> User | None:
        """Поиск по нормализованному e-mail без учёта регистра."""
        ...

    async def add(self, user: User) -> None:
        """Занятый e-mail даёт `IdentityError(email_taken)`."""
        ...

    async def update(self, user: User) -> None: ...
    async def get_for_update(self, user_id: str) -> User | None:
        """Свежая строка пользователя с блокировкой до конца транзакции: запись по ней не затрёт чужую правку."""
        ...

    async def count(self) -> int: ...
    async def lock_active_admins(self) -> int:
        """Блокирует строки действующих админов установки до конца транзакции и возвращает их число."""
        ...

    async def get_by_identity(self, provider: str, subject: str) -> User | None: ...
    async def add_identity(self, identity: UserIdentity) -> None: ...
    async def list_identities(self, user_id: str) -> list[UserIdentity]: ...


class IUserDirectory(Protocol):
    async def get(self, user_id: str) -> UserListing | None: ...
    async def search(
        self, *, q: str | None, status: UserStatus | None, limit: int, offset: int
    ) -> tuple[list[UserListing], int]:
        """Страница пользователей (новые первыми) и общее число под тем же фильтром.

        `q` ищет подстроку в имени и e-mail без учёта регистра.
        """
        ...


class IFirstAdminRepository(Protocol):
    async def create_first_admin(self, user: User, password_hash: str) -> None:
        """Атомарно создаёт пользователя-админа с паролем, если админа установки ещё нет.

        Параллельные вызовы сериализуются: успешным будет ровно один, остальные получат
        `IdentityError(setup_already_done)`. Занятый e-mail даёт `IdentityError(email_taken)`.
        """
        ...


class ICredentialRepository(Protocol):
    async def get_hash(self, user_id: str) -> str | None: ...
    async def set_hash(self, user_id: str, password_hash: str) -> None: ...


class ISessionRepository(Protocol):
    async def add(self, session: Session) -> None: ...
    async def get(self, id_hash: str) -> Session | None: ...
    async def touch(self, id_hash: str, now: datetime, expires_at: datetime) -> None: ...
    async def delete(self, id_hash: str) -> None: ...
    async def list_for_user(self, user_id: str) -> list[Session]: ...
    async def delete_for_user(self, user_id: str, *, except_id_hash: str | None = None) -> int: ...
    async def delete_expired(self, now: datetime) -> int: ...


class IApiTokenRepository(Protocol):
    async def add(self, token: ApiToken) -> None: ...
    async def get_by_hash(self, token_hash: str) -> ApiToken | None: ...
    async def list_for_user(self, user_id: str) -> list[ApiToken]: ...
    async def delete(self, user_id: str, token_id: str) -> bool: ...
    async def touch(self, token_id: str, now: datetime) -> None: ...


class IAuthTokenRepository(Protocol):
    async def add(self, token: AuthToken) -> None: ...
    async def delete_expired(self, now: datetime) -> int: ...
    async def consume(self, token_hash: str, kind: AuthTokenKind, now: datetime) -> AuthToken | None:
        """Атомарно помечает токен использованным; просроченный или использованный даёт None."""
        ...

    async def invalidate_for_user(self, user_id: str, kind: AuthTokenKind, now: datetime) -> int:
        """Помечает использованными все ещё не использованные токены вида у пользователя; возвращает их число."""
        ...


class IRegistrationInviteRepository(Protocol):
    async def add(self, invite: RegistrationInvite) -> None: ...
    async def get(self, token_hash: str) -> RegistrationInvite | None:
        """Приглашение любого состояния; годность (срок, использование, адрес) решает вызывающий."""
        ...

    async def list(self, *, created_by: str | None = None, limit: int = 200) -> list[RegistrationInvite]:
        """Приглашения любого состояния, новые по сроку первыми."""
        ...

    async def revoke(self, invite_id: str) -> bool:
        """Удаляет неиспользованное приглашение; False, если такого нет или оно уже принято."""
        ...

    async def consume(self, token_hash: str, email: str, now: datetime) -> RegistrationInvite | None: ...


class ILoginAttemptRepository(Protocol):
    async def get(self, key: str) -> LoginAttempt | None: ...
    async def record_failure(self, key: str, now: datetime, delay_for: Callable[[int], timedelta]) -> LoginAttempt:
        """Атомарно увеличивает счётчик и назначает `next_allowed_at = now + delay_for(failures)`."""
        ...

    async def reset(self, key: str) -> None: ...
    async def delete_stale(self, before: datetime) -> int:
        """Удаляет счётчики без обновлений с момента `before`."""
        ...


class IMailOutboxRepository(Protocol):
    async def add(self, entry: MailOutboxEntry) -> None: ...
    async def list_active(self, now: datetime, *, limit: int = 100) -> list[MailOutboxEntry]:
        """Непросроченные письма, новые первыми."""
        ...

    async def delete(self, entry_id: str) -> bool: ...
    async def delete_expired(self, now: datetime) -> int: ...


class IOidcProviderRepository(Protocol):
    async def get(self, provider_id: str) -> OidcProvider | None: ...
    async def list(self, *, only_enabled: bool = False) -> list[OidcProvider]: ...
    async def save(self, provider: OidcProvider) -> None:
        """Создаёт или заменяет провайдера (`created_at` существующего не меняется)."""
        ...

    async def delete(self, provider_id: str) -> bool: ...


class IInstanceSettingsRepository(Protocol):
    async def get_all(self) -> Mapping[str, object]: ...
    async def set(self, key: str, value: object, *, source: str) -> None: ...


class IAuditLog(Protocol):
    async def record(
        self,
        action: str,
        *,
        actor_id: str | None,
        target: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        """Только дозапись: приложение не изменяет и не удаляет события. Значения секретных ключей
        в `details` вычёркиваются (`redact`)."""
        ...


class IAuditReader(Protocol):
    async def list(
        self, *, limit: int = 100, action: str | None = None, actor_id: str | None = None
    ) -> list[AuditEntry]:
        """События, новые первыми."""
        ...


class IPasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, password: str, password_hash: str) -> bool: ...
    def needs_rehash(self, password_hash: str) -> bool: ...


class IRateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_s: int) -> bool:
        """True, если попытка укладывается в лимит окна."""
        ...


class IMailSender(Protocol):
    @property
    def enabled(self) -> bool: ...
    async def send(self, to: str, subject: str, body: str) -> None: ...


class IActorResolver(Protocol):
    async def resolve(self, credentials: ActorCredentials) -> Actor | None:
        """Актор по предъявленным данным либо None, если этот способ входа их не распознал."""
        ...
