"""Postgres-репозитории identity: пользователи, внешние учётные записи, пароли, настройки установки."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hse_doc_studio.core.identity.entities import User, UserIdentity, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.infra.db.orm.identity import (
    InstanceSettingRow,
    PasswordCredentialRow,
    UserIdentityRow,
    UserRow,
)
from hse_doc_studio.infra.db.session import SessionProvider

FIRST_ADMIN_LOCK_KEY = 0x48534D33  # "HSM3"


def _user(row: UserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        email_normalized=row.email_normalized,
        name=row.name,
        status=UserStatus(row.status),
        created_at=row.created_at,
        email_verified=row.email_verified,
        is_instance_admin=row.is_instance_admin,
        locale=row.locale,
        last_login_at=row.last_login_at,
    )


def _user_values(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "email_normalized": user.email_normalized,
        "name": user.name,
        "status": user.status.value,
        "email_verified": user.email_verified,
        "is_instance_admin": user.is_instance_admin,
        "locale": user.locale,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }


def _identity(row: UserIdentityRow) -> UserIdentity:
    return UserIdentity(
        user_id=row.user_id,
        provider=row.provider,
        subject=row.subject,
        email=row.email,
        email_verified=row.email_verified,
    )


async def _insert_user(session: AsyncSession, user: User) -> None:
    # ON CONFLICT вместо перехвата IntegrityError: ошибка не ломает внешнюю транзакцию
    stmt = (
        pg_insert(UserRow)
        .values(**_user_values(user))
        .on_conflict_do_nothing(index_elements=[UserRow.email_normalized])
        .returning(UserRow.id)
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise IdentityError(IdentityErrorCode.email_taken)


async def _upsert_hash(session: AsyncSession, user_id: str, password_hash: str) -> None:
    stmt = pg_insert(PasswordCredentialRow).values(user_id=user_id, password_hash=password_hash)
    stmt = stmt.on_conflict_do_update(
        index_elements=[PasswordCredentialRow.user_id],
        set_={"password_hash": stmt.excluded.password_hash, "updated_at": func.now()},
    )
    await session.execute(stmt)


class SqlUserRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get(self, user_id: str) -> User | None:
        async with self._sessions.use() as session:
            row = await session.get(UserRow, user_id)
            return _user(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        async with self._sessions.use() as session:
            row = (
                await session.execute(select(UserRow).where(UserRow.email_normalized == normalize_email(email)))
            ).scalar_one_or_none()
            return _user(row) if row else None

    async def add(self, user: User) -> None:
        async with self._sessions.use() as session:
            await _insert_user(session, user)

    async def update(self, user: User) -> None:
        values = _user_values(user)
        del values["id"]
        async with self._sessions.use() as session:
            row = await session.get(UserRow, user.id)
            if row is None:
                raise IdentityError(IdentityErrorCode.forbidden)
            clash = (
                await session.execute(
                    select(UserRow.id).where(UserRow.email_normalized == user.email_normalized, UserRow.id != user.id)
                )
            ).first()
            if clash is not None:
                raise IdentityError(IdentityErrorCode.email_taken)
            for key, value in values.items():
                setattr(row, key, value)

    async def count(self) -> int:
        async with self._sessions.use() as session:
            return (await session.execute(select(func.count()).select_from(UserRow))).scalar_one()

    async def get_by_identity(self, provider: str, subject: str) -> User | None:
        async with self._sessions.use() as session:
            row = (
                await session.execute(
                    select(UserRow)
                    .join(UserIdentityRow, UserIdentityRow.user_id == UserRow.id)
                    .where(UserIdentityRow.provider == provider, UserIdentityRow.subject == subject)
                )
            ).scalar_one_or_none()
            return _user(row) if row else None

    async def add_identity(self, identity: UserIdentity) -> None:
        stmt = (
            pg_insert(UserIdentityRow)
            .values(
                provider=identity.provider,
                subject=identity.subject,
                user_id=identity.user_id,
                email=identity.email,
                email_verified=identity.email_verified,
            )
            .on_conflict_do_nothing(index_elements=[UserIdentityRow.provider, UserIdentityRow.subject])
            .returning(UserIdentityRow.subject)
        )
        async with self._sessions.use() as session:
            if (await session.execute(stmt)).scalar_one_or_none() is None:
                raise IdentityError(IdentityErrorCode.forbidden)

    async def list_identities(self, user_id: str) -> list[UserIdentity]:
        async with self._sessions.use() as session:
            rows = (
                await session.execute(
                    select(UserIdentityRow)
                    .where(UserIdentityRow.user_id == user_id)
                    .order_by(UserIdentityRow.provider, UserIdentityRow.subject)
                )
            ).scalars()
            return [_identity(row) for row in rows]


class SqlCredentialRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get_hash(self, user_id: str) -> str | None:
        async with self._sessions.use() as session:
            return (
                await session.execute(
                    select(PasswordCredentialRow.password_hash).where(PasswordCredentialRow.user_id == user_id)
                )
            ).scalar_one_or_none()

    async def set_hash(self, user_id: str, password_hash: str) -> None:
        async with self._sessions.use() as session:
            await _upsert_hash(session, user_id, password_hash)


class SqlFirstAdminRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def create_first_admin(self, user: User, password_hash: str) -> None:
        # Блокировка живёт до конца транзакции: второй вызов ждёт коммита первого и видит его админа.
        # Своя транзакция гарантирует, что лок снимается даже без внешнего UoW.
        async with self._sessions.begin(), self._sessions.use() as session:
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": FIRST_ADMIN_LOCK_KEY})
            exists = (
                await session.execute(select(UserRow.id).where(UserRow.is_instance_admin.is_(True)).limit(1))
            ).first()
            if exists is not None:
                raise IdentityError(IdentityErrorCode.setup_already_done)
            await _insert_user(session, user)
            await _upsert_hash(session, user.id, password_hash)


class SqlInstanceSettingsRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get_all(self) -> Mapping[str, object]:
        async with self._sessions.use() as session:
            rows = (await session.execute(select(InstanceSettingRow))).scalars()
            return {row.key: row.value for row in rows}

    async def set(self, key: str, value: object, *, source: str) -> None:
        stmt = pg_insert(InstanceSettingRow).values(key=key, value=value, source=source)
        stmt = stmt.on_conflict_do_update(
            index_elements=[InstanceSettingRow.key],
            set_={"value": stmt.excluded.value, "source": stmt.excluded.source, "updated_at": func.now()},
        )
        async with self._sessions.use() as session:
            await session.execute(stmt)
