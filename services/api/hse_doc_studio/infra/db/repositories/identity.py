"""Postgres-репозитории identity: пользователи, внешние учётные записи, пароли, настройки установки."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from sqlalchemy import ColumnElement, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hse_doc_studio.core.identity.entities import (
    User,
    UserFacets,
    UserIdentity,
    UserListing,
    UserPickQuery,
    UserQuery,
    UserStatus,
    facets_of,
)
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.listing import Found, Picked
from hse_doc_studio.infra.db.listing import Expr, contains_lower, fetch_page, ordering
from hse_doc_studio.infra.db.orm.identity import (
    InstanceSettingRow,
    PasswordCredentialRow,
    UserIdentityRow,
    UserRow,
)
from hse_doc_studio.infra.db.orm.orgs import GroupMemberRow, OrgMemberRow, OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
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
        commit_name=row.commit_name,
        commit_email=row.commit_email,
        commit_use_account_email=row.commit_use_account_email,
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
        "commit_name": user.commit_name,
        "commit_email": user.commit_email,
        "commit_use_account_email": user.commit_use_account_email,
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

    async def get_for_update(self, user_id: str) -> User | None:
        async with self._sessions.use() as session:
            row = (
                await session.execute(
                    select(UserRow)
                    .where(UserRow.id == user_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
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

    async def lock_active_admins(self) -> int:
        async with self._sessions.use() as session:
            rows = await session.execute(
                select(UserRow.id)
                .where(UserRow.is_instance_admin.is_(True), UserRow.status == UserStatus.active.value)
                .order_by(UserRow.id)
                .with_for_update()
            )
            return len(rows.all())

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

    async def delete_identity(self, user_id: str, provider: str) -> int:
        stmt = (
            delete(UserIdentityRow)
            .where(UserIdentityRow.user_id == user_id, UserIdentityRow.provider == provider)
            .returning(UserIdentityRow.subject)
        )
        async with self._sessions.use() as session:
            return len((await session.execute(stmt)).all())

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


async def _project_counts(session: AsyncSession, user_ids: list[str]) -> dict[str, int]:
    if not user_ids:
        return {}
    found = await session.execute(
        select(ProjectRow.owner_user_id, func.count())
        .where(ProjectRow.owner_user_id.in_(user_ids), ProjectRow.deleted_at.is_(None))
        .group_by(ProjectRow.owner_user_id)
    )
    return {owner: n for owner, n in found.all() if owner is not None}


# Поля сортировки списка людей; имя без учёта регистра, как его ищут.
_USER_SORT: dict[str, Expr] = {
    "name": func.lower(UserRow.name),
    "email": UserRow.email_normalized,
    "created_at": UserRow.created_at,
    "last_login_at": UserRow.last_login_at,
    "status": UserRow.status,
}


def _user_search(q: str) -> ColumnElement[bool]:
    # Выражения совпадают с индексами lower(name) и email_normalized (в том числе триграммными).
    return contains_lower(q, func.lower(UserRow.name), UserRow.email_normalized)


def _in_org(slug: str) -> ColumnElement[bool]:
    return UserRow.id.in_(
        select(OrgMemberRow.user_id).join(OrgRow, OrgRow.id == OrgMemberRow.org_id).where(OrgRow.slug == slug)
    )


def _user_conditions(query: UserQuery) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if query.q:
        conditions.append(_user_search(query.q))
    if query.statuses:
        conditions.append(UserRow.status.in_([s.value for s in query.statuses]))
    if query.is_admin is not None:
        conditions.append(UserRow.is_instance_admin.is_(query.is_admin))
    if query.org_slug is not None:
        conditions.append(_in_org(query.org_slug))
    return conditions


class SqlUserDirectory:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get(self, user_id: str) -> UserListing | None:
        async with self._sessions.use() as session:
            row = await session.get(UserRow, user_id)
            if row is None:
                return None
            counts = await _project_counts(session, [row.id])
            return UserListing(_user(row), counts.get(row.id, 0))

    async def search(self, query: UserQuery) -> Found[UserListing]:
        stmt = select(UserRow).where(*_user_conditions(query)).order_by(*ordering(query.sort, _USER_SORT, UserRow.id))
        async with self._sessions.use() as session:
            found, total = await fetch_page(session, stmt, query.window)
            rows = [row for (row,) in found]
            # Число проектов только для строк страницы, а не для всей установки.
            counts = await _project_counts(session, [r.id for r in rows])
            return Found([UserListing(_user(r), counts.get(r.id, 0)) for r in rows], total)

    async def facets(self, query: UserQuery) -> UserFacets:
        # Одна группировка по статусу и роли (не больше восьми строк) под общими условиями: поиск и организация.
        # Фильтры статуса и роли применяются уже к строкам, каждый счётчик без своего.
        common = replace(query, statuses=(), is_admin=None)
        stmt = (
            select(UserRow.status, UserRow.is_instance_admin, func.count())
            .where(*_user_conditions(common))
            .group_by(UserRow.status, UserRow.is_instance_admin)
        )
        async with self._sessions.use() as session:
            rows = [(UserStatus(status), bool(admin), n) for status, admin, n in (await session.execute(stmt)).all()]
        return facets_of(rows, query)

    async def pick(self, query: UserPickQuery) -> Picked[User]:
        stmt = select(UserRow)
        if query.q:
            stmt = stmt.where(_user_search(query.q))
        if query.status is not None:
            stmt = stmt.where(UserRow.status == query.status.value)
        if query.not_in_org_slug is not None:
            stmt = stmt.where(~_in_org(query.not_in_org_slug))
        if query.not_in_group_id is not None:
            stmt = stmt.where(
                UserRow.id.not_in(
                    select(GroupMemberRow.user_id).where(GroupMemberRow.group_id == query.not_in_group_id)
                )
            )
        stmt = stmt.order_by(func.lower(UserRow.name), UserRow.id).limit(query.limit + 1)
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return Picked.of([_user(r) for r in rows], query.limit)


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

    async def delete(self, key: str) -> None:
        async with self._sessions.use() as session:
            await session.execute(delete(InstanceSettingRow).where(InstanceSettingRow.key == key))

    async def get_secret(self, key: str) -> str | None:
        async with self._sessions.use() as session:
            row = await session.get(InstanceSettingRow, key)
            return row.secret_enc if row else None

    async def set_secret(self, key: str, token: str, *, source: str) -> None:
        stmt = pg_insert(InstanceSettingRow).values(key=key, value=True, source=source, secret_enc=token)
        stmt = stmt.on_conflict_do_update(
            index_elements=[InstanceSettingRow.key],
            set_={
                "value": stmt.excluded.value,
                "source": stmt.excluded.source,
                "secret_enc": stmt.excluded.secret_enc,
                "updated_at": func.now(),
            },
        )
        async with self._sessions.use() as session:
            await session.execute(stmt)
