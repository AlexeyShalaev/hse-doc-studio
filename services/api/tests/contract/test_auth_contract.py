"""Контракт репозиториев входа: одни и те же проверки на InMemory и Postgres."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from hse_doc_studio.core.identity.entities import (
    ApiToken,
    AuthToken,
    AuthTokenKind,
    MailKind,
    MailOutboxEntry,
    OidcProvider,
    RegistrationInvite,
    Session,
    TokenScope,
)
from hse_doc_studio.core.identity.protocols import (
    IApiTokenRepository,
    IAuditLog,
    IAuditReader,
    IAuthTokenRepository,
    ILoginAttemptRepository,
    IMailOutboxRepository,
    IOidcProviderRepository,
    IRegistrationInviteRepository,
    ISessionRepository,
    IUserRepository,
)
from pytest_lazy_fixtures import lf

from tests.contract.test_identity_contract import make_user
from tests.fakes.auth import (
    InMemoryApiTokenRepository,
    InMemoryAuditLog,
    InMemoryAuthTokenRepository,
    InMemoryLoginAttemptRepository,
    InMemoryMailOutboxRepository,
    InMemoryOidcProviderRepository,
    InMemoryRegistrationInviteRepository,
    InMemorySessionRepository,
)
from tests.fakes.identity import InMemoryUserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


class _Audit(IAuditLog, IAuditReader):
    pass


@dataclass
class Repos:
    users: IUserRepository
    sessions: ISessionRepository
    api_tokens: IApiTokenRepository
    auth_tokens: IAuthTokenRepository
    invites: IRegistrationInviteRepository
    attempts: ILoginAttemptRepository
    outbox: IMailOutboxRepository
    oidc: IOidcProviderRepository
    audit: _Audit


@pytest_asyncio.fixture
async def memory_repos() -> Repos:
    return Repos(
        InMemoryUserRepository(),
        InMemorySessionRepository(),
        InMemoryApiTokenRepository(),
        InMemoryAuthTokenRepository(),
        InMemoryRegistrationInviteRepository(),
        InMemoryLoginAttemptRepository(),
        InMemoryMailOutboxRepository(),
        InMemoryOidcProviderRepository(),
        InMemoryAuditLog(),  # type: ignore[arg-type]
    )


@pytest_asyncio.fixture
async def pg_repos(pg_migrated_engine: AsyncEngine) -> Repos:
    from hse_doc_studio.infra.db.engine import create_sessionmaker
    from hse_doc_studio.infra.db.repositories.auth import (
        SqlApiTokenRepository,
        SqlAuditLog,
        SqlAuthTokenRepository,
        SqlLoginAttemptRepository,
        SqlMailOutboxRepository,
        SqlOidcProviderRepository,
        SqlRegistrationInviteRepository,
        SqlSessionRepository,
    )
    from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
    from hse_doc_studio.infra.db.session import SessionProvider

    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    return Repos(
        SqlUserRepository(sessions),
        SqlSessionRepository(sessions),
        SqlApiTokenRepository(sessions),
        SqlAuthTokenRepository(sessions),
        SqlRegistrationInviteRepository(sessions),
        SqlLoginAttemptRepository(sessions),
        SqlMailOutboxRepository(sessions),
        SqlOidcProviderRepository(sessions),
        SqlAuditLog(sessions),  # type: ignore[arg-type]
    )


@pytest.fixture(
    params=[lf("memory_repos"), pytest.param(lf("pg_repos"), marks=pytest.mark.pg)], ids=["in_memory", "pg"]
)
def repos(request: pytest.FixtureRequest) -> Repos:
    return request.param


@pytest_asyncio.fixture
async def user(repos: Repos) -> str:
    await repos.users.add(make_user("u1"))
    await repos.users.add(make_user("u2"))
    return "u1"


def make_session(id_hash: str, user_id: str = "u1", *, created: datetime = NOW, ttl: timedelta = HOUR) -> Session:
    return Session(
        id_hash=id_hash,
        user_id=user_id,
        csrf_token=f"csrf-{id_hash}",
        created_at=created,
        last_seen_at=created,
        expires_at=created + ttl,
        ip="10.0.0.1",
        user_agent="pytest",
    )


async def test__session__add_get_touch_delete(repos: Repos, user: str) -> None:
    session = make_session("s1")
    await repos.sessions.add(session)
    assert await repos.sessions.get("s1") == session
    assert await repos.sessions.get("missing") is None

    later = NOW + timedelta(minutes=5)
    await repos.sessions.touch("s1", later, later + HOUR)
    touched = await repos.sessions.get("s1")
    assert touched == replace(session, last_seen_at=later, expires_at=later + HOUR)

    await repos.sessions.delete("s1")
    assert await repos.sessions.get("s1") is None


async def test__session__list_and_delete_for_user__keeps_excepted_and_other_users(repos: Repos, user: str) -> None:
    await repos.sessions.add(make_session("s1", created=NOW))
    await repos.sessions.add(make_session("s2", created=NOW + timedelta(seconds=1)))
    await repos.sessions.add(make_session("s3", created=NOW + timedelta(seconds=2)))
    await repos.sessions.add(make_session("other", "u2"))
    assert [s.id_hash for s in await repos.sessions.list_for_user("u1")] == ["s1", "s2", "s3"]

    assert await repos.sessions.delete_for_user("u1", except_id_hash="s2") == 2
    assert [s.id_hash for s in await repos.sessions.list_for_user("u1")] == ["s2"]
    assert await repos.sessions.get("other") is not None
    assert await repos.sessions.delete_for_user("u1") == 1


async def test__session__delete_expired__removes_only_expired(repos: Repos, user: str) -> None:
    await repos.sessions.add(make_session("old", ttl=timedelta(minutes=1)))
    await repos.sessions.add(make_session("fresh", ttl=HOUR))
    assert await repos.sessions.delete_expired(NOW + timedelta(minutes=2)) == 1
    assert await repos.sessions.get("old") is None
    assert await repos.sessions.get("fresh") is not None


def make_api_token(token_id: str, user_id: str = "u1", token_hash: str = "") -> ApiToken:
    return ApiToken(
        id=token_id,
        user_id=user_id,
        name=f"token {token_id}",
        token_hash=token_hash or f"hash-{token_id}",
        prefix="hse_abc",
        scopes=frozenset({TokenScope.api, TokenScope.git_read}),
        created_at=NOW,
        expires_at=NOW + timedelta(days=30),
    )


async def test__api_token__add_lookup_touch(repos: Repos, user: str) -> None:
    token = make_api_token("t1")
    await repos.api_tokens.add(token)
    assert await repos.api_tokens.get_by_hash("hash-t1") == token
    assert await repos.api_tokens.get_by_hash("nope") is None
    await repos.api_tokens.touch("t1", NOW + HOUR)
    found = await repos.api_tokens.get_by_hash("hash-t1")
    assert found is not None
    assert found.last_used_at == NOW + HOUR


async def test__api_token__delete_requires_owner(repos: Repos, user: str) -> None:
    await repos.api_tokens.add(make_api_token("t1"))
    assert not await repos.api_tokens.delete("u2", "t1")
    assert await repos.api_tokens.get_by_hash("hash-t1") is not None
    assert await repos.api_tokens.delete("u1", "t1")
    assert not await repos.api_tokens.delete("u1", "t1")
    assert await repos.api_tokens.list_for_user("u1") == []


async def test__auth_token__consume__single_use_and_kind_checked(repos: Repos, user: str) -> None:
    token = AuthToken(token_hash="h", kind=AuthTokenKind.reset_password, user_id="u1", expires_at=NOW + HOUR)
    await repos.auth_tokens.add(token)
    assert await repos.auth_tokens.consume("h", AuthTokenKind.verify_email, NOW) is None
    consumed = await repos.auth_tokens.consume("h", AuthTokenKind.reset_password, NOW)
    assert consumed == replace(token, used_at=NOW)
    assert await repos.auth_tokens.consume("h", AuthTokenKind.reset_password, NOW) is None


async def test__auth_token__expired__cannot_be_consumed_and_is_cleaned(repos: Repos, user: str) -> None:
    await repos.auth_tokens.add(AuthToken("h", AuthTokenKind.setup, None, NOW + HOUR))
    assert await repos.auth_tokens.consume("h", AuthTokenKind.setup, NOW + HOUR) is None
    assert await repos.auth_tokens.delete_expired(NOW + HOUR) == 1
    assert await repos.auth_tokens.delete_expired(NOW + HOUR) == 0


async def test__auth_token__parallel_consume__exactly_one_wins(repos: Repos, user: str) -> None:
    await repos.auth_tokens.add(AuthToken("h", AuthTokenKind.verify_email, "u1", NOW + HOUR))
    results = await asyncio.gather(*(repos.auth_tokens.consume("h", AuthTokenKind.verify_email, NOW) for _ in range(8)))
    assert sum(1 for r in results if r is not None) == 1


async def test__invite__consume__matches_email_once(repos: Repos, user: str) -> None:
    invite = RegistrationInvite("h", "new@example.test", "u1", NOW + HOUR)
    await repos.invites.add(invite)
    assert await repos.invites.consume("h", "other@example.test", NOW) is None
    consumed = await repos.invites.consume("h", " NEW@example.test ", NOW)
    assert consumed == replace(invite, used_at=NOW)
    assert await repos.invites.consume("h", "new@example.test", NOW) is None


async def test__invite__without_email_and_expired(repos: Repos, user: str) -> None:
    await repos.invites.add(RegistrationInvite("any", None, "u1", NOW + HOUR))
    await repos.invites.add(RegistrationInvite("late", None, "u1", NOW + HOUR))
    assert await repos.invites.consume("late", "x@example.test", NOW + HOUR) is None
    assert await repos.invites.consume("any", "x@example.test", NOW) is not None


async def test__invite__parallel_consume__exactly_one_wins(repos: Repos, user: str) -> None:
    await repos.invites.add(RegistrationInvite("h", None, "u1", NOW + HOUR))
    results = await asyncio.gather(*(repos.invites.consume("h", "a@example.test", NOW) for _ in range(8)))
    assert sum(1 for r in results if r is not None) == 1


def _delay(failures: int) -> timedelta:
    return timedelta(seconds=min(2 ** (failures - 1), 900))


async def test__login_attempts__failures_grow_delay_and_reset(repos: Repos) -> None:
    assert await repos.attempts.get("a@x|1.1.1.1") is None
    first = await repos.attempts.record_failure("a@x|1.1.1.1", NOW, _delay)
    assert (first.failures, first.next_allowed_at) == (1, NOW + timedelta(seconds=1))
    third = None
    for _ in range(2):
        third = await repos.attempts.record_failure("a@x|1.1.1.1", NOW, _delay)
    assert third is not None
    assert (third.failures, third.next_allowed_at) == (3, NOW + timedelta(seconds=4))
    assert await repos.attempts.get("a@x|1.1.1.1") == third

    other = await repos.attempts.record_failure("a@x|2.2.2.2", NOW, _delay)
    assert other.failures == 1

    await repos.attempts.reset("a@x|1.1.1.1")
    assert await repos.attempts.get("a@x|1.1.1.1") is None
    assert await repos.attempts.get("a@x|2.2.2.2") is not None


async def test__login_attempts__parallel_failures__are_all_counted(repos: Repos) -> None:
    await asyncio.gather(*(repos.attempts.record_failure("k", NOW, _delay) for _ in range(6)))
    attempt = await repos.attempts.get("k")
    assert attempt is not None
    assert attempt.failures == 6
    assert attempt.next_allowed_at == NOW + _delay(6)


async def test__login_attempts__delete_stale(repos: Repos) -> None:
    await repos.attempts.record_failure("old", NOW, _delay)
    await repos.attempts.record_failure("new", NOW + HOUR, _delay)
    assert await repos.attempts.delete_stale(NOW + timedelta(minutes=30)) == 1
    assert await repos.attempts.get("old") is None
    assert await repos.attempts.get("new") is not None


def make_mail(entry_id: str, created: datetime, ttl: timedelta = HOUR) -> MailOutboxEntry:
    return MailOutboxEntry(
        id=entry_id,
        kind=MailKind.invite,
        to_email="to@example.test",
        link=f"https://studio.test/invite/{entry_id}",
        created_at=created,
        expires_at=created + ttl,
    )


async def test__mail_outbox__lists_active_newest_first_and_cleans_expired(repos: Repos) -> None:
    await repos.outbox.add(make_mail("m1", NOW))
    await repos.outbox.add(make_mail("m2", NOW + timedelta(minutes=1)))
    await repos.outbox.add(make_mail("gone", NOW - HOUR, ttl=timedelta(minutes=10)))
    active = await repos.outbox.list_active(NOW + timedelta(minutes=2))
    assert [e.id for e in active] == ["m2", "m1"]
    assert [e.id for e in await repos.outbox.list_active(NOW + timedelta(minutes=2), limit=1)] == ["m2"]
    assert await repos.outbox.delete_expired(NOW) == 1
    assert await repos.outbox.delete("m1")
    assert not await repos.outbox.delete("m1")


def make_provider(provider_id: str, label: str = "Corp", *, enabled: bool = True) -> OidcProvider:
    return OidcProvider(
        id=provider_id,
        label=label,
        issuer="https://idp.example.test",
        client_id="client",
        client_secret_enc="hs1:cipher",  # noqa: S106 — шифртекст-заглушка
        created_at=NOW,
        enabled=enabled,
    )


async def test__oidc__save_get_list_delete(repos: Repos) -> None:
    await repos.oidc.save(make_provider("corp", "Corp"))
    await repos.oidc.save(make_provider("alt", "Alt", enabled=False))
    assert await repos.oidc.get("corp") == make_provider("corp", "Corp")
    assert [p.id for p in await repos.oidc.list()] == ["alt", "corp"]
    assert [p.id for p in await repos.oidc.list(only_enabled=True)] == ["corp"]
    assert await repos.oidc.delete("alt")
    assert not await repos.oidc.delete("alt")
    assert await repos.oidc.get("alt") is None


async def test__oidc__save_existing__replaces_fields_but_keeps_created_at(repos: Repos) -> None:
    await repos.oidc.save(make_provider("corp"))
    changed = replace(make_provider("corp", "Renamed"), created_at=NOW + HOUR, auto_provision=True)
    await repos.oidc.save(changed)
    stored = await repos.oidc.get("corp")
    assert stored == replace(changed, created_at=NOW)


async def test__audit__record_then_list_newest_first_with_filters(repos: Repos) -> None:
    await repos.audit.record("login.ok", actor_id="u1", target="user:u1", details={"ip": "10.0.0.1"})
    await repos.audit.record("login.fail", actor_id=None, details={"email": "a@x"})
    await repos.audit.record("login.ok", actor_id="u2")
    entries = await repos.audit.list()
    assert [e.action for e in entries] == ["login.ok", "login.fail", "login.ok"]
    assert entries[2].target == "user:u1"
    assert dict(entries[2].details) == {"ip": "10.0.0.1"}
    assert [e.actor_id for e in await repos.audit.list(action="login.ok")] == ["u2", "u1"]
    assert [e.action for e in await repos.audit.list(actor_id="u1")] == ["login.ok"]
    assert len(await repos.audit.list(limit=2)) == 2


async def test__audit__details_with_secret_keys__are_redacted(repos: Repos) -> None:
    await repos.audit.record(
        "token.create",
        actor_id="u1",
        details={"name": "ci", "token": "hse_secret", "nested": {"Password": "p", "keep": [{"client_secret": "s"}]}},
    )
    (entry,) = await repos.audit.list()
    assert dict(entry.details) == {
        "name": "ci",
        "token": "[redacted]",
        "nested": {"Password": "[redacted]", "keep": [{"client_secret": "[redacted]"}]},
    }
