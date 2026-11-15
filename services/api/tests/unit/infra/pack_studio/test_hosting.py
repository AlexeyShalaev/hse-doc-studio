"""API хостинга Студии шаблонов на фейковом хостинге (`httpx.MockTransport`): PR, форк, статус проверок, права."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind, RemoteTarget
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.providers import GitProvider
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteUrl, parse_remote_url
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.git_flow import CheckState, CiState, HostingRepo
from hse_doc_studio.infra.pack_studio.hosting import HttpPackHosting

TOKEN = "ghp_secret0123456789abcdefABCDEF0123"
CRED = uuid4()
GH = HostingRepo(GitProvider.github, "acme/packs", "https://github.com", "https://api.github.com")
GL = HostingRepo(GitProvider.gitlab, "fcs/packs", "https://gitlab.example.org", "https://gitlab.example.org/api/v4")


class _Access:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def get(self, credential_id: UUID, *, project_id: UUID | None) -> GitCredential | None:
        return GitCredential(
            id=credential_id,
            kind=GitCredentialKind.pat,
            label="t",
            host="github.com",
            username=None,
            status=CredentialStatus.ok,
            created_at=datetime.now(UTC),
        )

    async def get_secret(self, credential_id: UUID, *, project_id: UUID | None, remote: RemoteUrl) -> Secret:
        if credential_id != CRED:
            raise NotFoundError("no")
        self.asked.append(remote.display_url)
        return Secret(TOKEN)


Handler = Callable[[httpx.Request], httpx.Response]


def _hosting(handler: Handler, *, access: _Access | None = None) -> HttpPackHosting:
    return HttpPackHosting(access or _Access(), timeout_s=5.0, transport=httpx.MockTransport(handler))


def _target(url: str = "https://github.com/acme/packs.git", credential: UUID | None = CRED) -> RemoteTarget:
    return RemoteTarget(url=parse_remote_url(url), credential_id=credential)


async def test__open_pull_request__posts_with_bearer_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"number": 12, "html_url": "https://github.com/acme/packs/pull/12"})

    pull = await _hosting(handler).open_pull_request(
        GH, _target(), head="acme:pack-studio/a/b", base="main", title="t", body="b"
    )

    assert (pull.number, pull.url, pull.created) == (12, "https://github.com/acme/packs/pull/12", True)
    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.github.com/repos/acme/packs/pulls"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == {
        "title": "t",
        "head": "acme:pack-studio/a/b",
        "base": "main",
        "body": "b",
        "maintainer_can_modify": True,
    }


async def test__open_pull_request__already_open__finds_the_existing_one() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                422, json={"message": "Validation Failed", "errors": [{"message": "A pull request already exists"}]}
            )
        assert request.url.params["head"] == "acme:b"
        return httpx.Response(200, json=[{"number": 3, "html_url": "https://github.com/acme/packs/pull/3"}])

    pull = await _hosting(handler).open_pull_request(GH, _target(), head="acme:b", base="main", title="t", body="b")

    assert (pull.number, pull.created) == (3, False)


@pytest.mark.parametrize("status", [401, 403, 404])
async def test__open_pull_request__denied__is_pr_permission_missing_without_the_token(status: int) -> None:
    hosting = _hosting(lambda _r: httpx.Response(status, json={"message": f"denied {TOKEN[:4]}"}))

    with pytest.raises(PackStudioError) as caught:
        await hosting.open_pull_request(GH, _target(), head="acme:b", base="main", title="t", body="b")

    assert caught.value.code is PackStudioErrorCode.pr_permission_missing
    assert TOKEN not in str(caught.value.detail) + str(caught.value.ctx)


async def test__permissions__github_push_flag_and_unknown_when_hidden() -> None:
    allowed = _hosting(lambda _r: httpx.Response(200, json={"permissions": {"push": True}}))
    hidden = _hosting(lambda _r: httpx.Response(404, json={}))

    assert (await allowed.permissions(GH, _target())).can_push is True
    assert (await hidden.permissions(GH, _target())).can_push is None


async def test__permissions__gitlab_developer_can_push_reporter_cannot() -> None:
    def level(value: int) -> Handler:
        return lambda _r: httpx.Response(200, json={"permissions": {"project_access": {"access_level": value}}})

    target = _target("https://gitlab.example.org/fcs/packs.git")

    assert (await _hosting(level(30)).permissions(GL, target)).can_push is True
    assert (await _hosting(level(20)).permissions(GL, target)).can_push is False


async def test__fork__existing_fork_of_this_repo__found_without_creating() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "anna"})
        return httpx.Response(
            200,
            json={
                "fork": True,
                "full_name": "anna/packs",
                "clone_url": "https://github.com/anna/packs.git",
                "parent": {"full_name": "acme/packs"},
            },
        )

    fork = await _hosting(handler).fork(GH, _target(), create=True)

    assert fork is not None
    assert (fork.path, fork.clone_url) == ("anna/packs", "https://github.com/anna/packs.git")
    assert calls == ["GET /user", "GET /repos/anna/packs"]


async def test__fork__none_yet__created_on_request_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "anna"})
        if request.method == "POST":
            return httpx.Response(
                202, json={"full_name": "anna/packs", "clone_url": "https://github.com/anna/packs.git"}
            )
        return httpx.Response(404, json={})

    assert await _hosting(handler).fork(GH, _target(), create=False) is None
    made = await _hosting(handler).fork(GH, _target(), create=True)
    assert made is not None
    assert made.path == "anna/packs"


async def test__ci_status__github_runs_and_statuses_merged() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/check-runs"):
            return httpx.Response(
                200,
                json={
                    "check_runs": [
                        {"name": "packs", "status": "completed", "conclusion": "success", "output": {"title": "ok"}},
                        {"name": "build", "status": "queued"},
                    ]
                },
            )
        return httpx.Response(200, json={"statuses": [{"context": "ci", "state": "error", "description": "boom"}]})

    report = await _hosting(handler).ci_status(GH, _target(), sha="abc", branch="b")

    assert report.state is CiState.failure
    assert [(c.name, c.state, c.summary) for c in report.checks] == [
        ("packs", CheckState.success, "ok"),
        ("build", CheckState.queued, None),
        ("ci", CheckState.failure, "boom"),
    ]
    assert report.web_url == "https://github.com/acme/packs/commit/abc/checks"


async def test__ci_status__fine_grained_token_without_checks_api__uses_statuses_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/check-runs"):
            return httpx.Response(403, json={})
        return httpx.Response(200, json={"statuses": [{"context": "ci", "state": "pending"}]})

    report = await _hosting(handler).ci_status(GH, _target(), sha="abc", branch="b")

    assert report.available is True
    assert report.state is CiState.pending


async def test__ci_status__github_both_denied__unavailable_with_link() -> None:
    report = await _hosting(lambda _r: httpx.Response(403, json={})).ci_status(GH, _target(), sha="abc", branch="b")

    assert report.available is False
    assert report.reason == "ci_status_unavailable"
    assert report.web_url == "https://github.com/acme/packs/commit/abc/checks"


async def test__ci_status__gitlab_latest_pipeline_jobs_with_private_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/pipelines"):
            return httpx.Response(
                200, json=[{"id": 4, "status": "failed"}, {"id": 9, "status": "running", "web_url": "https://gl/p/9"}]
            )
        return httpx.Response(
            200, json=[{"name": "check", "status": "running", "stage": "test", "web_url": "https://gl/j/1"}]
        )

    report = await _hosting(handler).ci_status(
        GL, _target("https://gitlab.example.org/fcs/packs.git"), sha="abc", branch="b"
    )

    assert report.state is CiState.pending
    assert [(c.name, c.state) for c in report.checks] == [("check", CheckState.running)]
    assert report.web_url == "https://gl/p/9"
    assert seen[0].url.raw_path.startswith(b"/api/v4/projects/fcs%2Fpacks/pipelines")
    assert seen[1].url.raw_path.startswith(b"/api/v4/projects/fcs%2Fpacks/pipelines/9/jobs")
    assert all(r.headers["private-token"] == TOKEN for r in seen)


async def test__ci_status__gitlab_no_pipeline__none() -> None:
    report = await _hosting(lambda _r: httpx.Response(200, json=[])).ci_status(
        GL, _target("https://gitlab.example.org/fcs/packs.git"), sha="abc", branch="b"
    )

    assert report.state is CiState.none
    assert report.available is True


async def test__plain_http_api__refused_without_consent() -> None:
    repo = HostingRepo(GitProvider.github, "acme/packs", "http://ghe.local", "http://ghe.local/api/v3")

    with pytest.raises(GitSyncError) as caught:
        await _hosting(lambda _r: httpx.Response(200, json={})).permissions(repo, _target())

    assert caught.value.code is GitErrorCode.url_scheme_forbidden


async def test__missing_credential__is_credentials_missing() -> None:
    with pytest.raises(GitSyncError) as caught:
        await _hosting(lambda _r: httpx.Response(200, json={})).permissions(GH, _target(credential=uuid4()))

    assert caught.value.code is GitErrorCode.credentials_missing


async def test__huge_body__ignored_not_buffered() -> None:
    hosting = _hosting(lambda _r: httpx.Response(200, content=b"[" + b"1," * 1_100_000 + b"1]"))

    assert (await hosting.permissions(GH, _target())).can_push is None


async def test__timeout__is_a_git_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(GitSyncError) as caught:
        await _hosting(handler).permissions(GH, _target())

    assert caught.value.code is GitErrorCode.timeout


# ── срез T22: одобрение запуска, состояние PR, чей токен, синхронизация форка ──


async def test__ci_status__fork_run_awaiting_approval__reported_in_words_not_as_none() -> None:
    sha = "a" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/check-runs"):
            return httpx.Response(200, json={"check_runs": []})
        if path.endswith("/status"):
            return httpx.Response(200, json={"statuses": []})
        if path == "/repos/acme/packs/actions/runs":
            assert request.url.params["head_sha"] == sha
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "name": "CI",
                            "status": "completed",
                            "conclusion": "action_required",
                            "html_url": "https://r/1",
                        },
                        {"name": "Docs", "status": "completed", "conclusion": "success", "html_url": None},
                    ]
                },
            )
        return httpx.Response(404, json={})

    report = await _hosting(handler).ci_status(GH, _target(), sha=sha, branch="b")

    assert report.state is CiState.awaiting_approval
    assert [(c.name, c.state, c.url) for c in report.checks] == [("CI", CheckState.awaiting_approval, "https://r/1")]


async def test__ci_status__runs_api_unavailable__checks_still_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"statuses": [{"context": "ci", "state": "success"}]})
        return httpx.Response(403, json={})

    report = await _hosting(handler).ci_status(GH, _target(), sha="b" * 40, branch=None)

    assert report.state is CiState.success


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"state": "closed", "merged": True}, "merged"),
        ({"state": "closed", "merged": False, "merged_at": None}, "closed"),
        ({"state": "open", "merged": False}, "open"),
    ],
)
async def test__pull_request_state__open_merged_closed(body: dict[str, object], expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/packs/pulls/7"
        return httpx.Response(200, json=body)

    state = await _hosting(handler).pull_request_state(GH, _target(), 7)

    assert state is not None
    assert state.value == expected


async def test__pull_request_state__not_github_or_denied__none() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={})

    assert await _hosting(handler).pull_request_state(GH, _target(), 7) is None
    assert await _hosting(handler).pull_request_state(GL, _target(), 7) is None


async def test__account__classic_token__login_and_scopes_from_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/user"
        return httpx.Response(200, json={"login": "studio-bot"}, headers={"X-OAuth-Scopes": "public_repo, read:org"})

    account = await _hosting(handler).account(GH, _target())

    assert account is not None
    assert (account.login, account.scopes) == ("studio-bot", ("public_repo", "read:org"))


async def test__account__fine_grained_token__no_scopes_header() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"login": "studio-bot"})

    account = await _hosting(handler).account(GH, _target())

    assert account is not None
    assert account.scopes is None


async def test__account__rejected_token__none() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Bad credentials"})

    assert await _hosting(handler).account(GH, _target()) is None


async def test__sync_fork__posts_merge_upstream_and_never_raises() -> None:
    seen: list[httpx.Request] = []
    fork = HostingRepo(GitProvider.github, "bot/packs", "https://github.com", "https://api.github.com")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"merge_type": "fast-forward"})

    def broken(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    synced = await _hosting(handler).sync_fork(fork, _target("https://github.com/bot/packs.git"), branch="master")

    assert synced is True
    (request,) = seen
    assert (request.method, request.url.path) == ("POST", "/repos/bot/packs/merge-upstream")
    assert json.loads(request.content) == {"branch": "master"}
    assert await _hosting(broken).sync_fork(fork, _target("https://github.com/bot/packs.git"), branch="master") is False
