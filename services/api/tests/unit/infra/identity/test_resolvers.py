from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hse_doc_studio.core.access.entities import Actor, ActorKind, ActorSource
from hse_doc_studio.core.identity.entities import ActorCredentials, Session, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.infra.identity.resolvers import (
    BearerActorResolver,
    ChainActorResolver,
    LocalActorResolver,
    SessionCookieResolver,
)
from hse_doc_studio.use_cases.identity.sessions import SessionService

from tests.fakes.auth import InMemorySessionRepository
from tests.fakes.identity import InMemoryIdentityStore, InMemoryUserRepository

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
SECRET = "s3cret-cookie-value"


async def _setup(*, status: UserStatus = UserStatus.active, admin: bool = False) -> SessionCookieResolver:
    users = InMemoryUserRepository(InMemoryIdentityStore())
    sessions = InMemorySessionRepository()
    email = "ann@example.org"
    await users.add(
        User(
            id="u1",
            email=email,
            email_normalized=normalize_email(email),
            name="Ann",
            status=status,
            created_at=NOW,
            email_verified=True,
            is_instance_admin=admin,
        )  # fmt: skip
    )
    await sessions.add(
        Session(
            id_hash=hash_token(SECRET),
            user_id="u1",
            csrf_token="c",
            created_at=NOW,
            last_seen_at=NOW,
            expires_at=NOW + timedelta(days=7),
        )  # fmt: skip
    )
    return SessionCookieResolver(SessionService(sessions, users, clock=lambda: NOW))


async def test_cookie_resolver_valid_session_gives_user_actor() -> None:
    resolver = await _setup(admin=True)

    actor = await resolver.resolve(ActorCredentials(session_secret=SECRET))

    # В акторе подпись коммитов: настоящий адрес наружу не уходит, пока человек сам не разрешил
    assert actor == Actor.user("u1", "Ann", "u1@noreply.localhost", is_instance_admin=True, source=ActorSource.session)


async def test_cookie_resolver_unknown_or_missing_secret_gives_none() -> None:
    resolver = await _setup()

    assert await resolver.resolve(ActorCredentials(session_secret="other")) is None
    assert await resolver.resolve(ActorCredentials()) is None


async def test_cookie_resolver_disabled_user_gives_none() -> None:
    resolver = await _setup(status=UserStatus.disabled)

    assert await resolver.resolve(ActorCredentials(session_secret=SECRET)) is None


async def test_chain_first_recognised_wins_and_anonymous_is_none() -> None:
    cookie = await _setup()

    chain = ChainActorResolver([cookie, BearerActorResolver()])

    assert (await chain.resolve(ActorCredentials(session_secret=SECRET))) is not None
    assert await chain.resolve(ActorCredentials(bearer_token="pat-123")) is None
    assert await chain.resolve(ActorCredentials()) is None


async def test_local_resolver_always_gives_local_actor() -> None:
    actor = await LocalActorResolver().resolve(ActorCredentials())

    assert actor is not None
    assert actor.kind is ActorKind.local
