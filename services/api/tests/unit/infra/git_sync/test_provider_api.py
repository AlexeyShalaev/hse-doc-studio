"""Определение провайдера и проверка токена против локальных серверов, которые отвечают как GitLab, GitHub и Gitea."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.entities import TokenState
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import DetectionRequest, IntrospectionRequest
from hse_doc_studio.core.git_sync.providers import ApiDetection, GitProvider
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.infra.git_sync.provider_api import HttpProviderDetector, HttpTokenIntrospector
from hse_doc_studio.infra.git_sync.tls_certificates import TlsCertificateService

from tests.fixtures.git_remote import ApiHandler, ApiReply, GitHttpServer
from tests.fixtures.tls import make_ca_signed, make_self_signed

_TOKEN = "glpat-CANARYtokenValue1234567890"
_GITLAB_VERSION = {"version": "17.3.1", "revision": "abc1234", "kas": {"enabled": False}}


def _json(status: int, body: object, **headers: str) -> ApiReply:
    return status, headers, body


def _constant(status: int, body: object, **headers: str) -> ApiHandler:
    return lambda _headers: _json(status, body, **headers)


@pytest.fixture
def server_factory(tmp_path: Path) -> Iterator[Callable[..., GitHttpServer]]:
    servers: list[GitHttpServer] = []

    def make(api: dict[str, ApiHandler], *, tls: bool = False) -> GitHttpServer:
        material = make_self_signed(tmp_path / f"tls-{len(servers)}") if tls else None
        server = GitHttpServer(root=tmp_path / "root", token=None, tls=material, api=api)
        server.start()
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.stop()


def _request(
    server: GitHttpServer, *segments: str, providers: tuple[GitProvider, ...] | None = None
) -> DetectionRequest:
    return DetectionRequest(
        secure=server.tls is not None,
        host="127.0.0.1",
        port=server.port,
        segments=segments or ("team", "paper.git"),
        providers=providers or (GitProvider.gitlab, GitProvider.gitea, GitProvider.github),
    )


# --- определение провайдера --------------------------------------------------------------------------------------


async def test__detect__gitlab_version__returns_provider_version_and_api_base(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory({"/api/v4/version": _constant(200, _GITLAB_VERSION)})

    found = await HttpProviderDetector(3.0).detect(_request(server))

    assert found == ApiDetection(GitProvider.gitlab, "17.3.1", f"{server.base_url}/api/v4")


async def test__detect__gitlab_demands_login__is_recognized_by_its_headers_without_version(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory(
        {"/api/v4/version": _constant(401, {"message": "401 Unauthorized"}, **{"X-Gitlab-Meta": '{"version":"1"}'})}
    )

    found = await HttpProviderDetector(3.0).detect(_request(server))

    assert found == ApiDetection(GitProvider.gitlab, None, f"{server.base_url}/api/v4")


async def test__detect__plain_401_without_gitlab_headers__is_not_gitlab(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory({"/api/v4/version": _constant(401, {"message": "401 Unauthorized"})})

    assert await HttpProviderDetector(3.0).detect(_request(server)) is None


async def test__detect__gitea_version__is_recognized(server_factory: Callable[..., GitHttpServer]) -> None:
    server = server_factory({"/api/v1/version": _constant(200, {"version": "1.22.3"})})

    found = await HttpProviderDetector(3.0).detect(_request(server))

    assert found == ApiDetection(GitProvider.gitea, "1.22.3", f"{server.base_url}/api/v1")


async def test__detect__github_enterprise_header__is_recognized(server_factory: Callable[..., GitHttpServer]) -> None:
    server = server_factory(
        {"/api/v3": _constant(200, {"current_user_url": "x"}, **{"X-GitHub-Enterprise-Version": "3.13.2"})}
    )

    found = await HttpProviderDetector(3.0).detect(_request(server))

    assert found == ApiDetection(GitProvider.github, "3.13.2", f"{server.base_url}/api/v3")


async def test__detect__subpath_installation__finds_the_prefix_and_derives_api_base_from_it(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory({"/gitlab/api/v4/version": _constant(200, _GITLAB_VERSION)})

    found = await HttpProviderDetector(3.0).detect(_request(server, "gitlab", "team", "paper.git"))

    assert found == ApiDetection(GitProvider.gitlab, "17.3.1", f"{server.base_url}/gitlab/api/v4")


async def test__detect__nothing_known_answers__is_none(server_factory: Callable[..., GitHttpServer]) -> None:
    server = server_factory({"/api/v4/version": _constant(404, {"error": "not found"})})

    assert await HttpProviderDetector(3.0).detect(_request(server)) is None


async def test__detect__server_with_html_instead_of_json__is_none(server_factory: Callable[..., GitHttpServer]) -> None:
    server = server_factory({"/api/v4/version": _constant(200, "<html></html>")})

    assert await HttpProviderDetector(3.0).detect(_request(server)) is None


async def test__detect__restricted_to_one_provider__does_not_ask_the_others(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory({"/api/v1/version": _constant(200, {"version": "1.22.3"})})

    found = await HttpProviderDetector(3.0).detect(_request(server, providers=(GitProvider.gitlab,)))

    assert found is None
    assert all("/api/v1/" not in request.path for request in server.requests)


async def test__detect__sends_no_credentials_and_does_not_follow_redirects(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory({"/api/v4/version": _constant(302, {}, Location="https://elsewhere.invalid/")})

    assert await HttpProviderDetector(3.0).detect(_request(server)) is None
    assert all(
        "authorization" not in request.headers and "private-token" not in request.headers for request in server.requests
    )


async def test__detect__answers_are_cached_for_the_same_request(server_factory: Callable[..., GitHttpServer]) -> None:
    server = server_factory({"/api/v4/version": _constant(200, _GITLAB_VERSION)})
    detector = HttpProviderDetector(3.0)

    await detector.detect(_request(server))
    count = len(server.requests)
    await detector.detect(_request(server))

    assert len(server.requests) == count


async def test__detect__host_that_does_not_answer__is_none() -> None:
    request = DetectionRequest(
        secure=False, host="127.0.0.1", port=1, segments=("a", "b"), providers=(GitProvider.gitlab,)
    )

    assert await HttpProviderDetector(1.0).detect(request) is None


async def test__detect__self_signed_server_without_trust__is_none_and_with_trust_is_found(
    server_factory: Callable[..., GitHttpServer], tmp_path: Path
) -> None:
    server = server_factory({"/api/v4/version": _constant(200, _GITLAB_VERSION)}, tls=True)
    assert server.tls is not None
    ca_file = tmp_path / "trust.pem"
    ca_file.write_text(server.tls.cert_pem, encoding="ascii")

    untrusted = await HttpProviderDetector(3.0).detect(_request(server))
    trusted = await HttpProviderDetector(3.0).detect(
        DetectionRequest(**{**_request(server).__dict__, "ca_file": ca_file})
    )

    assert untrusted is None
    assert trusted is not None
    assert trusted.version == "17.3.1"


# --- проверка токена -------------------------------------------------------------------------------------------


def _introspect(server: GitHttpServer, provider: GitProvider, api: str, **kwargs: object) -> IntrospectionRequest:
    return IntrospectionRequest(provider=provider, api_base=f"{server.base_url}{api}", token=Secret(_TOKEN), **kwargs)  # type: ignore[arg-type]


def _gitlab_routes(
    *, own: ApiHandler, user: ApiHandler | None = None, by_id: ApiHandler | None = None
) -> dict[str, ApiHandler]:
    routes = {"/api/v4/personal_access_tokens/self": own}
    if user is not None:
        routes["/api/v4/user"] = user
    if by_id is not None:
        routes["/api/v4/users/77"] = by_id
    return routes


def _gitlab_token(**overrides: object) -> dict[str, object]:
    return {
        "id": 9,
        "name": "HSE Studio",
        "revoked": False,
        "active": True,
        "user_id": 77,
        "scopes": ["read_repository", "write_repository"],
        "expires_at": "2099-01-22",
        **overrides,
    }


async def test__gitlab_introspection__valid_token__returns_login_scopes_and_expiry(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory(
        _gitlab_routes(own=_constant(200, _gitlab_token()), user=_constant(200, {"username": "anna.petrova"}))
    )

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.gitlab, "/api/v4"))

    assert result.state is TokenState.valid
    assert (result.login, result.scopes) == ("anna.petrova", ("read_repository", "write_repository"))
    assert result.expires_at == datetime(2099, 1, 22, tzinfo=timezone.utc)
    assert {request.headers.get("private-token") for request in server.requests} == {_TOKEN}


async def test__gitlab_introspection__user_endpoint_forbidden__falls_back_to_the_user_by_id(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory(
        _gitlab_routes(
            own=_constant(200, _gitlab_token()),
            user=_constant(403, {"message": "403 Forbidden"}),
            by_id=_constant(200, {"username": "anna.petrova"}),
        )
    )

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.gitlab, "/api/v4"))

    assert result.login == "anna.petrova"


async def test__gitlab_introspection__login_not_available__stays_valid_without_login(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory(_gitlab_routes(own=_constant(200, _gitlab_token(expires_at=None))))

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.gitlab, "/api/v4"))

    assert (result.state, result.login, result.expires_at) == (TokenState.valid, None, None)


async def test__gitlab_introspection__past_expiry__is_expired(server_factory: Callable[..., GitHttpServer]) -> None:
    past = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
    server = server_factory(_gitlab_routes(own=_constant(200, _gitlab_token(expires_at=past))))

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.gitlab, "/api/v4"))

    assert result.state is TokenState.expired
    assert result.expires_at is not None


async def test__gitlab_introspection__revoked_token__is_rejected(server_factory: Callable[..., GitHttpServer]) -> None:
    server = server_factory(_gitlab_routes(own=_constant(200, _gitlab_token(revoked=True, active=False))))

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.gitlab, "/api/v4"))

    assert result.state is TokenState.rejected


@pytest.mark.parametrize(
    ("description", "state"),
    [
        ("Token is expired. You can either do re-authorization or token refresh.", TokenState.expired),
        ("Token was revoked. You have to re-authorize from the user.", TokenState.rejected),
    ],
)
async def test__gitlab_introspection__401__tells_expired_from_rejected(
    server_factory: Callable[..., GitHttpServer], description: str, state: TokenState
) -> None:
    body = {"error": "invalid_token", "error_description": description}
    server = server_factory(_gitlab_routes(own=_constant(401, body)))

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.gitlab, "/api/v4"))

    assert result.state is state


async def test__gitlab_introspection__old_server_without_endpoint__cannot_introspect_and_does_not_fail(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory(_gitlab_routes(own=_constant(404, {"message": "404 Not Found"})))

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.gitlab, "/api/v4"))

    assert (result.state, result.login, result.scopes) == (TokenState.unknown, None, None)


async def test__github_introspection__classic_token__returns_login_scopes_and_expiry(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory(
        {
            "/api/v3/user": _constant(
                200,
                {"login": "anna-petrova"},
                **{
                    "X-OAuth-Scopes": "repo, workflow",
                    "github-authentication-token-expiration": "2099-12-01 10:30:00 UTC",
                },
            )
        }
    )

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.github, "/api/v3"))

    assert result.state is TokenState.valid
    assert (result.login, result.scopes) == ("anna-petrova", ("repo", "workflow"))
    assert result.expires_at == datetime(2099, 12, 1, 10, 30, tzinfo=timezone.utc)
    assert {request.headers.get("authorization") for request in server.requests} == {f"Bearer {_TOKEN}"}


async def test__github_introspection__fine_grained_token_has_no_scopes_header__scopes_are_unknown(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory({"/api/v3/user": _constant(200, {"login": "anna-petrova"})})

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.github, "/api/v3"))

    assert (result.state, result.login, result.scopes) == (TokenState.valid, "anna-petrova", None)


async def test__github_introspection__bad_credentials__is_rejected(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory({"/api/v3/user": _constant(401, {"message": "Bad credentials"})})

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.github, "/api/v3"))

    assert result.state is TokenState.rejected


async def test__github_introspection__expiry_header_in_the_past__is_expired(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory(
        {
            "/api/v3/user": _constant(
                200, {"login": "a"}, **{"github-authentication-token-expiration": "2020-01-01 00:00:00 UTC"}
            )
        }
    )

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.github, "/api/v3"))

    assert result.state is TokenState.expired


async def test__gitea_introspection__valid_token__returns_login_without_scopes(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory({"/api/v1/user": _constant(200, {"login": "anna", "id": 4})})

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.gitea, "/api/v1"))

    assert (result.state, result.login, result.scopes) == (TokenState.valid, "anna", None)
    assert {request.headers.get("authorization") for request in server.requests} == {f"token {_TOKEN}"}


async def test__gitea_introspection__token_cannot_read_the_user__is_unknown_not_failed(
    server_factory: Callable[..., GitHttpServer],
) -> None:
    server = server_factory({"/api/v1/user": _constant(403, {"message": "token does not have required scope"})})

    result = await HttpTokenIntrospector(3.0).introspect(_introspect(server, GitProvider.gitea, "/api/v1"))

    assert result.state is TokenState.unknown


async def test__introspection__provider_without_a_way_to_check__is_unknown() -> None:
    request = IntrospectionRequest(GitProvider.bitbucket, "https://api.bitbucket.org/2.0", Secret(_TOKEN))

    assert (await HttpTokenIntrospector(3.0).introspect(request)).state is TokenState.unknown


async def test__introspection__nobody_listens__raises_offline() -> None:
    request = IntrospectionRequest(GitProvider.gitlab, "http://127.0.0.1:1/api/v4", Secret(_TOKEN))

    with pytest.raises(GitSyncError) as error:
        await HttpTokenIntrospector(1.0).introspect(request)

    assert error.value.code is GitErrorCode.offline


async def test__introspection__self_signed_server__raises_untrusted_with_the_certificate_and_works_once_trusted(
    server_factory: Callable[..., GitHttpServer], tmp_path: Path
) -> None:
    server = server_factory(_gitlab_routes(own=_constant(200, _gitlab_token())), tls=True)
    assert server.tls is not None
    introspector = HttpTokenIntrospector(3.0, TlsCertificateService(3.0))

    with pytest.raises(GitSyncError) as error:
        await introspector.introspect(_introspect(server, GitProvider.gitlab, "/api/v4"))
    ca_file = tmp_path / "trust.pem"
    ca_file.write_text(server.tls.cert_pem, encoding="ascii")
    trusted = await introspector.introspect(_introspect(server, GitProvider.gitlab, "/api/v4", ca_file=ca_file))

    assert error.value.code is GitErrorCode.tls_untrusted_ca
    certificate = error.value.ctx["certificate"]
    assert certificate.self_signed is True  # type: ignore[attr-defined]
    assert certificate.fingerprint_sha256.startswith("SHA256:")  # type: ignore[attr-defined]
    assert trusted.state is TokenState.valid


async def test__introspection__certificate_issued_by_an_unknown_ca__is_untrusted_and_trusted_through_that_ca(
    tmp_path: Path,
) -> None:
    material = make_ca_signed(tmp_path / "ca")
    server = GitHttpServer(
        root=tmp_path / "root", token=None, tls=material, api=_gitlab_routes(own=_constant(200, _gitlab_token()))
    )
    server.start()
    try:
        ca_file = tmp_path / "ca.pem"
        ca_file.write_text(material.ca_pem or "", encoding="ascii")
        introspector = HttpTokenIntrospector(3.0, TlsCertificateService(3.0))

        with pytest.raises(GitSyncError) as error:
            await introspector.introspect(_introspect(server, GitProvider.gitlab, "/api/v4"))
        trusted = await introspector.introspect(_introspect(server, GitProvider.gitlab, "/api/v4", ca_file=ca_file))
    finally:
        server.stop()

    assert error.value.code is GitErrorCode.tls_untrusted_ca
    assert error.value.ctx["certificate"].self_signed is False  # type: ignore[attr-defined]
    assert trusted.state is TokenState.valid
