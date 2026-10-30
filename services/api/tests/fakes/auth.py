"""InMemory-реализации портов входа: те же правила, что у Postgres, без БД."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from hse_doc_studio.core.identity.entities import (
    ApiToken,
    AuditEntry,
    AuditQuery,
    AuthToken,
    AuthTokenKind,
    InviteQuery,
    LoginAttempt,
    MailOutboxEntry,
    OidcProvider,
    RegistrationInvite,
    Session,
    invite_state,
)
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.redaction import redact
from hse_doc_studio.core.listing import Found
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver

from tests.fakes.identity import InMemoryIdentityStore, InMemoryUserRepository
from tests.fakes.listing import matches, ordered, page


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._items: dict[str, Session] = {}

    async def add(self, session: Session) -> None:
        self._items[session.id_hash] = session

    async def get(self, id_hash: str) -> Session | None:
        return self._items.get(id_hash)

    async def touch(self, id_hash: str, now: datetime, expires_at: datetime) -> None:
        if id_hash in self._items:
            self._items[id_hash] = replace(self._items[id_hash], last_seen_at=now, expires_at=expires_at)

    async def delete(self, id_hash: str) -> None:
        self._items.pop(id_hash, None)

    async def list_for_user(self, user_id: str) -> list[Session]:
        found = [s for s in self._items.values() if s.user_id == user_id]
        return sorted(found, key=lambda s: (s.created_at, s.id_hash))

    async def delete_for_user(self, user_id: str, *, except_id_hash: str | None = None) -> int:
        doomed = [s.id_hash for s in self._items.values() if s.user_id == user_id and s.id_hash != except_id_hash]
        for key in doomed:
            del self._items[key]
        return len(doomed)

    async def delete_expired(self, now: datetime) -> int:
        doomed = [s.id_hash for s in self._items.values() if s.expires_at <= now]
        for key in doomed:
            del self._items[key]
        return len(doomed)


class InMemoryApiTokenRepository:
    def __init__(self) -> None:
        self._items: dict[str, ApiToken] = {}

    async def add(self, token: ApiToken) -> None:
        self._items[token.id] = token

    async def get_by_hash(self, token_hash: str) -> ApiToken | None:
        return next((t for t in self._items.values() if t.token_hash == token_hash), None)

    async def list_for_user(self, user_id: str) -> list[ApiToken]:
        found = [t for t in self._items.values() if t.user_id == user_id]
        return sorted(found, key=lambda t: (t.created_at, t.id))

    async def delete(self, user_id: str, token_id: str) -> bool:
        token = self._items.get(token_id)
        if token is None or token.user_id != user_id:
            return False
        del self._items[token_id]
        return True

    async def touch(self, token_id: str, now: datetime) -> None:
        if token_id in self._items:
            self._items[token_id] = replace(self._items[token_id], last_used_at=now)


class InMemoryAuthTokenRepository:
    """Между проверкой и отметкой нет await: в одном цикле событий потребление атомарно."""

    def __init__(self) -> None:
        self._items: dict[str, AuthToken] = {}

    async def add(self, token: AuthToken) -> None:
        self._items[token.token_hash] = token

    async def consume(self, token_hash: str, kind: AuthTokenKind, now: datetime) -> AuthToken | None:
        token = self._items.get(token_hash)
        if token is None or token.kind is not kind or token.used_at is not None or token.expires_at <= now:
            return None
        used = replace(token, used_at=now)
        self._items[token_hash] = used
        return used

    async def invalidate_for_user(self, user_id: str, kind: AuthTokenKind, now: datetime) -> int:
        pending = [k for k, t in self._items.items() if t.user_id == user_id and t.kind is kind and t.used_at is None]
        for key in pending:
            self._items[key] = replace(self._items[key], used_at=now)
        return len(pending)

    async def delete_expired(self, now: datetime) -> int:
        doomed = [key for key, t in self._items.items() if t.expires_at <= now]
        for key in doomed:
            del self._items[key]
        return len(doomed)


class InMemoryRegistrationInviteRepository:
    def __init__(self) -> None:
        self._items: dict[str, RegistrationInvite] = {}
        # slug -> id организации для фильтра `org`; тест задаёт сам.
        self.org_ids: dict[str, str] = {}

    async def add(self, invite: RegistrationInvite) -> None:
        email = normalize_email(invite.email) if invite.email else None
        self._items[invite.token_hash] = replace(invite, email=email, id=invite.id or invite.token_hash[:32])

    async def get(self, token_hash: str) -> RegistrationInvite | None:
        return self._items.get(token_hash)

    async def get_by_id(self, invite_id: str) -> RegistrationInvite | None:
        return next((i for i in self._items.values() if i.id == invite_id), None)

    async def page(self, query: InviteQuery) -> Found[RegistrationInvite]:
        org_id = self.org_ids.get(query.org_slug, "") if query.org_slug is not None else None
        found = [
            i
            for i in self._items.values()
            if matches(query.q, i.email)
            and (not query.states or invite_state(i, query.now) in query.states)
            and (org_id is None or i.org_id == org_id)
            and (query.created_by is None or i.created_by == query.created_by)
        ]
        keys = {"expires_at": lambda i: i.expires_at, "email": lambda i: i.email.lower() if i.email else None}
        return page(ordered(found, query.sort, keys, lambda i: i.id), query.window)

    async def revoke(self, invite_id: str) -> bool:
        for key, invite in self._items.items():
            if invite.id == invite_id and invite.used_at is None:
                del self._items[key]
                return True
        return False

    async def consume(self, token_hash: str, email: str, now: datetime) -> RegistrationInvite | None:
        invite = self._items.get(token_hash)
        if invite is None or invite.used_at is not None or invite.expires_at <= now:
            return None
        if invite.email is not None and invite.email != normalize_email(email):
            return None
        used = replace(invite, used_at=now)
        self._items[token_hash] = used
        return used


class InMemoryLoginAttemptRepository:
    def __init__(self) -> None:
        self._items: dict[str, LoginAttempt] = {}

    async def get(self, key: str) -> LoginAttempt | None:
        return self._items.get(key)

    async def record_failure(self, key: str, now: datetime, delay_for: Callable[[int], timedelta]) -> LoginAttempt:
        failures = (self._items[key].failures if key in self._items else 0) + 1
        attempt = LoginAttempt(key=key, failures=failures, updated_at=now, next_allowed_at=now + delay_for(failures))
        self._items[key] = attempt
        return attempt

    async def reset(self, key: str) -> None:
        self._items.pop(key, None)

    async def delete_stale(self, before: datetime) -> int:
        doomed = [key for key, a in self._items.items() if a.updated_at < before]
        for key in doomed:
            del self._items[key]
        return len(doomed)


class InMemoryMailOutboxRepository:
    def __init__(self) -> None:
        self._items: dict[str, MailOutboxEntry] = {}

    async def add(self, entry: MailOutboxEntry) -> None:
        self._items[entry.id] = entry

    async def list_active(self, now: datetime, *, limit: int = 100) -> list[MailOutboxEntry]:
        alive = [e for e in self._items.values() if e.expires_at > now]
        return sorted(alive, key=lambda e: (-e.created_at.timestamp(), e.id))[:limit]

    async def delete(self, entry_id: str) -> bool:
        return self._items.pop(entry_id, None) is not None

    async def delete_expired(self, now: datetime) -> int:
        doomed = [key for key, e in self._items.items() if e.expires_at <= now]
        for key in doomed:
            del self._items[key]
        return len(doomed)


class InMemoryOidcProviderRepository:
    def __init__(self) -> None:
        self._items: dict[str, OidcProvider] = {}

    async def get(self, provider_id: str) -> OidcProvider | None:
        return self._items.get(provider_id)

    async def list(self, *, only_enabled: bool = False) -> list[OidcProvider]:
        found = [p for p in self._items.values() if p.enabled or not only_enabled]
        return sorted(found, key=lambda p: (p.label, p.id))

    async def save(self, provider: OidcProvider) -> None:
        existing = self._items.get(provider.id)
        self._items[provider.id] = replace(provider, created_at=existing.created_at) if existing else provider

    async def delete(self, provider_id: str) -> bool:
        return self._items.pop(provider_id, None) is not None


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._next_id = 1

    async def record(
        self,
        action: str,
        *,
        actor_id: str | None,
        target: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        entry = AuditEntry(
            id=self._next_id,
            at=datetime.now(UTC),
            action=action,
            actor_id=actor_id,
            target=target,
            details=copy.deepcopy(redact(details or {})),
        )
        self._next_id += 1
        self._entries.append(entry)

    async def list(
        self, *, limit: int = 100, action: str | None = None, actor_id: str | None = None
    ) -> list[AuditEntry]:
        found = [
            e
            for e in reversed(self._entries)
            if (action is None or e.action == action) and (actor_id is None or e.actor_id == actor_id)
        ]
        return found[:limit]

    async def query(self, query: AuditQuery) -> list[AuditEntry]:
        found = [
            e
            for e in reversed(self._entries)
            if (query.actor_id is None or e.actor_id == query.actor_id)
            and (not query.action_prefix or e.action.startswith(query.action_prefix))
            and (query.target is None or e.target == query.target)
            and (query.since is None or e.at >= query.since)
            and (query.until is None or e.at < query.until)
            and (query.before_id is None or e.id < query.before_id)
        ]
        return found[: query.limit]

    async def purge_before(self, cutoff: datetime) -> int:
        kept = [e for e in self._entries if e.at >= cutoff]
        purged = len(self._entries) - len(kept)
        self._entries = kept
        return purged


def empty_bearer_resolver() -> BearerActorResolver:
    """Bearer-резолвер без единого токена: опознаёт только пустоту, для тестов цепочки с cookie."""
    return BearerActorResolver(InMemoryApiTokenRepository(), InMemoryUserRepository(InMemoryIdentityStore()))
