"""Postgres-репозитории входа: сессии, токены, попытки, письма, приглашения, OIDC и аудит."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.identity.entities import (
    ApiToken,
    AuditEntry,
    AuthToken,
    AuthTokenKind,
    LoginAttempt,
    MailKind,
    MailOutboxEntry,
    OidcProvider,
    RegistrationInvite,
    Session,
    TokenScope,
)
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.redaction import redact
from hse_doc_studio.infra.db.orm.auth import (
    ApiTokenRow,
    AuditLogRow,
    AuthTokenRow,
    LoginAttemptRow,
    MailOutboxRow,
    OidcProviderRow,
    RegistrationInviteRow,
    SessionRow,
)
from hse_doc_studio.infra.db.session import SessionProvider


def _session(row: SessionRow) -> Session:
    return Session(
        id_hash=row.id_hash,
        user_id=row.user_id,
        csrf_token=row.csrf_token,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
        expires_at=row.expires_at,
        ip=row.ip,
        user_agent=row.user_agent,
    )


class SqlSessionRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, session: Session) -> None:
        async with self._sessions.use() as db:
            db.add(
                SessionRow(
                    id_hash=session.id_hash,
                    user_id=session.user_id,
                    csrf_token=session.csrf_token,
                    created_at=session.created_at,
                    last_seen_at=session.last_seen_at,
                    expires_at=session.expires_at,
                    ip=session.ip,
                    user_agent=session.user_agent,
                )
            )
            await db.flush()

    async def get(self, id_hash: str) -> Session | None:
        async with self._sessions.use() as db:
            row = await db.get(SessionRow, id_hash)
            return _session(row) if row else None

    async def touch(self, id_hash: str, now: datetime, expires_at: datetime) -> None:
        async with self._sessions.use() as db:
            await db.execute(
                update(SessionRow).where(SessionRow.id_hash == id_hash).values(last_seen_at=now, expires_at=expires_at)
            )

    async def delete(self, id_hash: str) -> None:
        async with self._sessions.use() as db:
            await db.execute(delete(SessionRow).where(SessionRow.id_hash == id_hash))

    async def list_for_user(self, user_id: str) -> list[Session]:
        async with self._sessions.use() as db:
            rows = (
                await db.execute(
                    select(SessionRow)
                    .where(SessionRow.user_id == user_id)
                    .order_by(SessionRow.created_at, SessionRow.id_hash)
                )
            ).scalars()
            return [_session(row) for row in rows]

    async def delete_for_user(self, user_id: str, *, except_id_hash: str | None = None) -> int:
        stmt = delete(SessionRow).where(SessionRow.user_id == user_id)
        if except_id_hash is not None:
            stmt = stmt.where(SessionRow.id_hash != except_id_hash)
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount  # type: ignore[attr-defined]

    async def delete_expired(self, now: datetime) -> int:
        async with self._sessions.use() as db:
            return (await db.execute(delete(SessionRow).where(SessionRow.expires_at <= now))).rowcount  # type: ignore[attr-defined]


def _api_token(row: ApiTokenRow) -> ApiToken:
    return ApiToken(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        token_hash=row.token_hash,
        prefix=row.prefix,
        scopes=frozenset(TokenScope(scope) for scope in row.scopes),
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
    )


class SqlApiTokenRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, token: ApiToken) -> None:
        async with self._sessions.use() as db:
            db.add(
                ApiTokenRow(
                    id=token.id,
                    user_id=token.user_id,
                    name=token.name,
                    token_hash=token.token_hash,
                    prefix=token.prefix,
                    scopes=sorted(scope.value for scope in token.scopes),
                    created_at=token.created_at,
                    expires_at=token.expires_at,
                    last_used_at=token.last_used_at,
                )
            )
            await db.flush()

    async def get_by_hash(self, token_hash: str) -> ApiToken | None:
        async with self._sessions.use() as db:
            row = (
                await db.execute(select(ApiTokenRow).where(ApiTokenRow.token_hash == token_hash))
            ).scalar_one_or_none()
            return _api_token(row) if row else None

    async def list_for_user(self, user_id: str) -> list[ApiToken]:
        async with self._sessions.use() as db:
            rows = (
                await db.execute(
                    select(ApiTokenRow)
                    .where(ApiTokenRow.user_id == user_id)
                    .order_by(ApiTokenRow.created_at, ApiTokenRow.id)
                )
            ).scalars()
            return [_api_token(row) for row in rows]

    async def delete(self, user_id: str, token_id: str) -> bool:
        async with self._sessions.use() as db:
            result = await db.execute(
                delete(ApiTokenRow)
                .where(ApiTokenRow.id == token_id, ApiTokenRow.user_id == user_id)
                .returning(ApiTokenRow.id)
            )
            return result.first() is not None

    async def touch(self, token_id: str, now: datetime) -> None:
        async with self._sessions.use() as db:
            await db.execute(update(ApiTokenRow).where(ApiTokenRow.id == token_id).values(last_used_at=now))


class SqlAuthTokenRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, token: AuthToken) -> None:
        async with self._sessions.use() as db:
            db.add(
                AuthTokenRow(
                    token_hash=token.token_hash,
                    kind=token.kind.value,
                    user_id=token.user_id,
                    expires_at=token.expires_at,
                    used_at=token.used_at,
                    payload=token.payload,
                )
            )
            await db.flush()

    async def consume(self, token_hash: str, kind: AuthTokenKind, now: datetime) -> AuthToken | None:
        # Один UPDATE с условием: параллельные потребители ждут блокировки строки и после коммита
        # первого не проходят условие `used_at IS NULL`, так что токен срабатывает ровно один раз.
        stmt = (
            update(AuthTokenRow)
            .where(
                AuthTokenRow.token_hash == token_hash,
                AuthTokenRow.kind == kind.value,
                AuthTokenRow.used_at.is_(None),
                AuthTokenRow.expires_at > now,
            )
            .values(used_at=now)
            .returning(AuthTokenRow)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return AuthToken(
                token_hash=row.token_hash,
                kind=AuthTokenKind(row.kind),
                user_id=row.user_id,
                expires_at=row.expires_at,
                used_at=row.used_at,
                payload=row.payload,
            )

    async def invalidate_for_user(self, user_id: str, kind: AuthTokenKind, now: datetime) -> int:
        stmt = (
            update(AuthTokenRow)
            .where(AuthTokenRow.user_id == user_id, AuthTokenRow.kind == kind.value, AuthTokenRow.used_at.is_(None))
            .values(used_at=now)
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount  # type: ignore[attr-defined]

    async def delete_expired(self, now: datetime) -> int:
        async with self._sessions.use() as db:
            return (await db.execute(delete(AuthTokenRow).where(AuthTokenRow.expires_at <= now))).rowcount  # type: ignore[attr-defined]


def _invite(row: RegistrationInviteRow) -> RegistrationInvite:
    return RegistrationInvite(
        token_hash=row.token_hash,
        email=row.email,
        created_by=row.created_by,
        expires_at=row.expires_at,
        used_at=row.used_at,
        id=row.id,
        org_id=row.org_id,
        org_role=row.org_role,
    )


class SqlRegistrationInviteRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, invite: RegistrationInvite) -> None:
        async with self._sessions.use() as db:
            db.add(
                RegistrationInviteRow(
                    token_hash=invite.token_hash,
                    email=normalize_email(invite.email) if invite.email else None,
                    created_by=invite.created_by,
                    expires_at=invite.expires_at,
                    used_at=invite.used_at,
                    id=invite.id or invite.token_hash[:32],
                    org_id=invite.org_id,
                    org_role=invite.org_role,
                )
            )
            await db.flush()

    async def get(self, token_hash: str) -> RegistrationInvite | None:
        async with self._sessions.use() as db:
            row = await db.get(RegistrationInviteRow, token_hash)
            return _invite(row) if row else None

    async def list(self, *, created_by: str | None = None, limit: int = 200) -> list[RegistrationInvite]:
        stmt = select(RegistrationInviteRow).order_by(RegistrationInviteRow.expires_at.desc(), RegistrationInviteRow.id)
        if created_by is not None:
            stmt = stmt.where(RegistrationInviteRow.created_by == created_by)
        async with self._sessions.use() as db:
            return [_invite(row) for row in (await db.execute(stmt.limit(limit))).scalars()]

    async def revoke(self, invite_id: str) -> bool:
        stmt = delete(RegistrationInviteRow).where(
            RegistrationInviteRow.id == invite_id, RegistrationInviteRow.used_at.is_(None)
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount > 0  # type: ignore[attr-defined]

    async def consume(self, token_hash: str, email: str, now: datetime) -> RegistrationInvite | None:
        stmt = (
            update(RegistrationInviteRow)
            .where(
                RegistrationInviteRow.token_hash == token_hash,
                RegistrationInviteRow.used_at.is_(None),
                RegistrationInviteRow.expires_at > now,
                or_(RegistrationInviteRow.email.is_(None), RegistrationInviteRow.email == normalize_email(email)),
            )
            .values(used_at=now)
            .returning(RegistrationInviteRow)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
            return _invite(row) if row else None


def _attempt(row: LoginAttemptRow) -> LoginAttempt:
    return LoginAttempt(
        key=row.key, failures=row.failures, updated_at=row.updated_at, next_allowed_at=row.next_allowed_at
    )


class SqlLoginAttemptRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get(self, key: str) -> LoginAttempt | None:
        async with self._sessions.use() as db:
            row = await db.get(LoginAttemptRow, key)
            return _attempt(row) if row else None

    async def record_failure(self, key: str, now: datetime, delay_for: Callable[[int], timedelta]) -> LoginAttempt:
        # Строка блокируется первым же UPSERT до конца транзакции, поэтому параллельные неудачи считаются по очереди.
        stmt = pg_insert(LoginAttemptRow).values(key=key, failures=1, updated_at=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=[LoginAttemptRow.key],
            set_={"failures": LoginAttemptRow.failures + 1, "updated_at": stmt.excluded.updated_at},
        ).returning(LoginAttemptRow.failures)
        async with self._sessions.begin(), self._sessions.use() as db:
            failures = (await db.execute(stmt)).scalar_one()
            next_allowed_at = now + delay_for(failures)
            await db.execute(
                update(LoginAttemptRow).where(LoginAttemptRow.key == key).values(next_allowed_at=next_allowed_at)
            )
        return LoginAttempt(key=key, failures=failures, updated_at=now, next_allowed_at=next_allowed_at)

    async def reset(self, key: str) -> None:
        async with self._sessions.use() as db:
            await db.execute(delete(LoginAttemptRow).where(LoginAttemptRow.key == key))

    async def delete_stale(self, before: datetime) -> int:
        async with self._sessions.use() as db:
            return (await db.execute(delete(LoginAttemptRow).where(LoginAttemptRow.updated_at < before))).rowcount  # type: ignore[attr-defined]


def _mail(row: MailOutboxRow) -> MailOutboxEntry:
    return MailOutboxEntry(
        id=row.id,
        kind=MailKind(row.kind),
        to_email=row.to_email,
        link=row.link,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


class SqlMailOutboxRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, entry: MailOutboxEntry) -> None:
        async with self._sessions.use() as db:
            db.add(
                MailOutboxRow(
                    id=entry.id,
                    kind=entry.kind.value,
                    to_email=entry.to_email,
                    link=entry.link,
                    created_at=entry.created_at,
                    expires_at=entry.expires_at,
                )
            )
            await db.flush()

    async def list_active(self, now: datetime, *, limit: int = 100) -> list[MailOutboxEntry]:
        async with self._sessions.use() as db:
            rows = (
                await db.execute(
                    select(MailOutboxRow)
                    .where(MailOutboxRow.expires_at > now)
                    .order_by(MailOutboxRow.created_at.desc(), MailOutboxRow.id)
                    .limit(limit)
                )
            ).scalars()
            return [_mail(row) for row in rows]

    async def delete(self, entry_id: str) -> bool:
        async with self._sessions.use() as db:
            result = await db.execute(
                delete(MailOutboxRow).where(MailOutboxRow.id == entry_id).returning(MailOutboxRow.id)
            )
            return result.first() is not None

    async def delete_expired(self, now: datetime) -> int:
        async with self._sessions.use() as db:
            return (await db.execute(delete(MailOutboxRow).where(MailOutboxRow.expires_at <= now))).rowcount  # type: ignore[attr-defined]


def _oidc(row: OidcProviderRow) -> OidcProvider:
    return OidcProvider(
        id=row.id,
        label=row.label,
        issuer=row.issuer,
        client_id=row.client_id,
        client_secret_enc=row.client_secret_enc,
        created_at=row.created_at,
        scopes=row.scopes,
        enabled=row.enabled,
        auto_provision=row.auto_provision,
    )


class SqlOidcProviderRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def get(self, provider_id: str) -> OidcProvider | None:
        async with self._sessions.use() as db:
            row = await db.get(OidcProviderRow, provider_id)
            return _oidc(row) if row else None

    async def list(self, *, only_enabled: bool = False) -> list[OidcProvider]:
        stmt = select(OidcProviderRow).order_by(OidcProviderRow.label, OidcProviderRow.id)
        if only_enabled:
            stmt = stmt.where(OidcProviderRow.enabled.is_(True))
        async with self._sessions.use() as db:
            return [_oidc(row) for row in (await db.execute(stmt)).scalars()]

    async def save(self, provider: OidcProvider) -> None:
        stmt = pg_insert(OidcProviderRow).values(
            id=provider.id,
            label=provider.label,
            issuer=provider.issuer,
            client_id=provider.client_id,
            client_secret_enc=provider.client_secret_enc,
            scopes=provider.scopes,
            enabled=provider.enabled,
            auto_provision=provider.auto_provision,
            created_at=provider.created_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[OidcProviderRow.id],
            set_={
                "label": stmt.excluded.label,
                "issuer": stmt.excluded.issuer,
                "client_id": stmt.excluded.client_id,
                "client_secret_enc": stmt.excluded.client_secret_enc,
                "scopes": stmt.excluded.scopes,
                "enabled": stmt.excluded.enabled,
                "auto_provision": stmt.excluded.auto_provision,
            },
        )
        async with self._sessions.use() as db:
            await db.execute(stmt)

    async def delete(self, provider_id: str) -> bool:
        async with self._sessions.use() as db:
            result = await db.execute(
                delete(OidcProviderRow).where(OidcProviderRow.id == provider_id).returning(OidcProviderRow.id)
            )
            return result.first() is not None


def _audit(row: AuditLogRow) -> AuditEntry:
    return AuditEntry(
        id=row.id, at=row.at, action=row.action, actor_id=row.actor_id, target=row.target, details=row.details
    )


class SqlAuditLog:
    """Только INSERT и SELECT: изменить или удалить событие нельзя ни из кода, ни из базы (триггер)."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def record(
        self,
        action: str,
        *,
        actor_id: str | None,
        target: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        async with self._sessions.use() as db:
            db.add(AuditLogRow(action=action, actor_id=actor_id, target=target, details=redact(details or {})))
            await db.flush()

    async def list(
        self, *, limit: int = 100, action: str | None = None, actor_id: str | None = None
    ) -> list[AuditEntry]:
        stmt = select(AuditLogRow).order_by(AuditLogRow.id.desc()).limit(limit)
        if action is not None:
            stmt = stmt.where(AuditLogRow.action == action)
        if actor_id is not None:
            stmt = stmt.where(AuditLogRow.actor_id == actor_id)
        async with self._sessions.use() as db:
            return [_audit(row) for row in (await db.execute(stmt)).scalars()]
