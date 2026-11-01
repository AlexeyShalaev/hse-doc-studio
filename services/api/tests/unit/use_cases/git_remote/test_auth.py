import base64
from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.entities import ActorCredentials, ApiToken, TokenScope
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.use_cases.git_remote.auth import (
    GitConcurrency,
    GitHttpAuthenticator,
    GitHttpError,
    GitHttpErrorKind,
    token_from_headers,
)

PAT = "hsd_pat_" + "a" * 32


def _basic(user: str, password: str) -> dict[str, str]:
    return {"authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def test__token_from_headers__basic_any_user_bearer_and_garbage() -> None:
    assert token_from_headers(_basic("anything", PAT)) == PAT
    assert token_from_headers({"authorization": f"Bearer {PAT}"}) == PAT
    assert token_from_headers(_basic("x", "password")) is None
    assert token_from_headers({"authorization": "Basic !!!"}) is None
    assert token_from_headers({"cookie": "hse_session=abc"}) is None
    assert token_from_headers({}) is None


class _Resolver:
    def __init__(self, actor: Actor | None) -> None:
        self.actor = actor
        self.seen: list[ActorCredentials] = []

    async def resolve(self, credentials: ActorCredentials) -> Actor | None:
        self.seen.append(credentials)
        return self.actor


class _Tokens:
    def __init__(self, token: ApiToken | None) -> None:
        self.token = token

    async def get_by_hash(self, token_hash: str) -> ApiToken | None:
        return self.token if self.token is not None and self.token.token_hash == token_hash else None


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    async def record(
        self, action: str, *, actor_id: str | None, target: str | None = None, details: object = None
    ) -> None:
        self.events.append((action, dict(details or {})))  # type: ignore[call-overload]


def _token(*scopes: TokenScope) -> ApiToken:
    return ApiToken(
        id="pat_1",
        user_id="u1",
        name="t",
        token_hash=hash_token(PAT),
        prefix="hsd_pat_aaa",
        scopes=frozenset(scopes),
        created_at=datetime.now(UTC),
    )


_USER = Actor.user("u1", source=ActorSource.pat, scopes=frozenset({"git:read"}))


async def test__authenticate__git_token__principal_and_only_bearer_reaches_resolver() -> None:
    resolver = _Resolver(_USER)
    auth = GitHttpAuthenticator(resolver, _Tokens(_token(TokenScope.git_read)), _Audit())  # type: ignore[arg-type]

    principal = await auth.authenticate({**_basic("x", PAT), "cookie": "hse_session=s"}, "1.2.3.4")

    assert principal.user_id == "u1"
    assert resolver.seen == [ActorCredentials(bearer_token=PAT)]


async def test__authenticate__api_only_token__scope_missing() -> None:
    auth = GitHttpAuthenticator(_Resolver(_USER), _Tokens(_token(TokenScope.api)), _Audit())  # type: ignore[arg-type]

    with pytest.raises(GitHttpError) as exc:
        await auth.authenticate({"authorization": f"Bearer {PAT}"}, "ip")
    assert exc.value.kind is GitHttpErrorKind.scope_missing


@pytest.mark.parametrize("actor", [None, Actor.user("u1", source=ActorSource.session)])
async def test__authenticate__unknown_disabled_or_not_pat__unauthorized_and_audited_once(actor: Actor | None) -> None:
    audit = _Audit()
    ticks = iter([0.0, 10.0, 1000.0])
    auth = GitHttpAuthenticator(
        _Resolver(actor), _Tokens(_token(TokenScope.git_read)), audit, monotonic=lambda: next(ticks)
    )  # type: ignore[arg-type]

    for _ in range(3):
        with pytest.raises(GitHttpError) as exc:
            await auth.authenticate({"authorization": f"Bearer {PAT}"}, "9.9.9.9")
        assert exc.value.kind is GitHttpErrorKind.unauthorized

    assert [a for a, _ in audit.events] == ["git.auth_failed", "git.auth_failed"]
    assert audit.events[1][1] == {"ip": "9.9.9.9", "count": 2}


async def test__authenticate__no_header__unauthorized_without_audit() -> None:
    audit = _Audit()
    auth = GitHttpAuthenticator(_Resolver(None), _Tokens(None), audit)  # type: ignore[arg-type]

    with pytest.raises(GitHttpError):
        await auth.authenticate({}, "ip")
    assert audit.events == []


def test__concurrency__per_user_limit_and_release() -> None:
    limit = GitConcurrency(2)

    assert limit.try_acquire("a")
    assert limit.try_acquire("a")
    assert not limit.try_acquire("a")
    assert limit.try_acquire("b")
    limit.release("a")
    assert limit.try_acquire("a")
