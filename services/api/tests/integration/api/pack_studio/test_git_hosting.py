"""Студия шаблонов, срез T6: PR GitHub, форк и ссылка compare, MR GitLab через push options, статус проверок.

Хостинг изображает настоящий `git http-backend` на 127.0.0.1 с токеном; API хостинга отвечает тот же сервер
(`GitHttpServer.api`), провайдер задан подменой в настройках хоста. В интернет ничего не ходит.
"""

from __future__ import annotations

import stat
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tests.fixtures.git_remote import ApiReply, GitHttpServer, run_git
from tests.integration.api.pack_studio.conftest import API, DRAFT_DIR, Stand
from tests.integration.api.pack_studio.test_git_workspace import _remote, _store

_DRAFT_TEX = f"{DRAFT_DIR}/files/report/main.tex"


def _reply(status: int, body: object) -> Callable[[Mapping[str, str]], ApiReply]:
    return lambda _headers: (status, {}, body)


async def _hosted_workspace(
    stand: Stand, server: GitHttpServer, provider: str, repo: str = "acme/packs.git"
) -> tuple[str, Path]:
    bare = server.create_repo(repo)
    bare.git("config", "uploadpack.allowFilter", "true")
    seed = _remote(stand.root / f"seed-{provider}")
    run_git("push", "--quiet", bare.url, "refs/heads/main:refs/heads/main", git_dir=seed.path)
    await stand.enable()
    assert (await stand.client.put("/api/v1/profile", json={"name": "Анна", "email": "anna@example.org"})).is_success
    settings = await stand.client.put(
        "/api/v1/git/host-settings", json={"host": "127.0.0.1", "port": server.port, "provider_override": provider}
    )
    assert settings.status_code == 200, settings.text
    credential = await stand.client.post(
        "/api/v1/git/credentials", json={"kind": "pat", "label": "Токен", "host": "127.0.0.1", "token": server.token}
    )
    assert credential.status_code == 201, credential.text
    resp = await stand.client.post(
        f"{API}/workspaces",
        json={"kind": "git", "url": server.url(repo), "credential_id": credential.json()["id"]},
    )
    assert resp.status_code == 202, resp.text
    ws = await stand.settled(resp.json()["id"])
    assert ws["state"] == "ready", ws
    ws_id = str(ws["id"])
    edited = await stand.client.put(stand.file_url(ws_id, _DRAFT_TEX), content=b"\\documentclass{article}\n% pr\n")
    assert edited.status_code == 200, edited.text
    return ws_id, bare.path


def _api_requests(server: GitHttpServer, prefix: str) -> list[Any]:
    return [r for r in server.requests if r.path.startswith(prefix)]


async def test__github__propose_opens_a_pull_request_with_the_token_only_in_the_header(
    stand: Stand, http_git_server_factory: Callable[..., GitHttpServer]
) -> None:
    server = http_git_server_factory()
    server.api["/api/v3/repos/acme/packs"] = _reply(200, {"permissions": {"push": True}})
    server.api["/api/v3/repos/acme/packs/pulls"] = _reply(
        201, {"number": 5, "html_url": f"{server.base_url}/acme/packs/pull/5"}
    )
    ws_id, bare = await _hosted_workspace(stand, server, "github")

    resp = await stand.client.post(f"{API}/workspaces/{ws_id}/git/propose", json={"title": "fix(packs): черновик"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pull_request"] == {"number": 5, "url": f"{server.base_url}/acme/packs/pull/5", "created": True}
    assert body["compare_url"] is None
    assert body["git"]["workspace"]["pr_number"] == 5  # noqa: PLR2004
    assert body["git"]["workspace"]["ci_status"] == "pending"
    branch = body["git"]["branch"]
    assert run_git("rev-parse", f"refs/heads/{branch}", git_dir=bare) == body["pushed_sha"]
    (pull,) = _api_requests(server, "/api/v3/repos/acme/packs/pulls")
    assert pull.method == "POST"
    assert pull.authorization == f"Bearer {server.token}"
    token = str(server.token)
    assert token not in resp.text
    store = _store(stand, ws_id)
    assert [p for p in store.rglob("*") if p.is_file() and token.encode() in p.read_bytes()] == []

    sha = body["pushed_sha"]
    server.api[f"/api/v3/repos/acme/packs/commits/{sha}/check-runs"] = _reply(
        200,
        {
            "check_runs": [
                {"name": "packs", "status": "completed", "conclusion": "failure", "html_url": "https://ci/1"},
                {"name": "lint", "status": "in_progress", "conclusion": None, "html_url": None},
            ]
        },
    )
    server.api[f"/api/v3/repos/acme/packs/commits/{sha}/status"] = _reply(
        200, {"statuses": [{"context": "ci/build", "state": "success", "description": "ok", "target_url": None}]}
    )
    checks = await stand.client.get(f"{API}/workspaces/{ws_id}/git/checks")
    card = await stand.client.get(f"{API}/workspaces/{ws_id}")

    assert checks.status_code == 200, checks.text
    assert checks.json()["state"] == "failure"
    assert [(c["name"], c["state"]) for c in checks.json()["checks"]] == [
        ("packs", "failure"),
        ("lint", "running"),
        ("ci/build", "success"),
    ]
    assert card.json()["ci_status"] == "failure"


async def test__github__no_push_right__asks_for_a_fork_then_pushes_there_and_links_compare(
    stand: Stand, http_git_server_factory: Callable[..., GitHttpServer]
) -> None:
    server = http_git_server_factory()
    server.api["/api/v3/repos/acme/packs"] = _reply(200, {"permissions": {"push": False}})
    server.api["/api/v3/repos/acme/packs/pulls"] = _reply(403, {"message": "Resource not accessible"})
    ws_id, upstream = await _hosted_workspace(stand, server, "github")
    fork = server.create_repo("anna/packs.git")

    refused = await stand.client.post(f"{API}/workspaces/{ws_id}/git/propose", json={})
    other_host = await stand.client.post(
        f"{API}/workspaces/{ws_id}/git/propose", json={"fork": {"url": "https://github.com/anna/packs.git"}}
    )
    resp = await stand.client.post(
        f"{API}/workspaces/{ws_id}/git/propose", json={"fork": {"url": server.url("anna/packs.git")}}
    )

    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "fork_required"
    assert refused.json()["can_create"] is True
    assert other_host.json()["code"] == "fork_required"
    assert resp.status_code == 200, resp.text
    body = resp.json()
    branch = body["git"]["branch"]
    assert body["pushed_to"] == server.url("anna/packs.git")
    assert fork.head(branch) == body["pushed_sha"]
    assert run_git("for-each-ref", "refs/heads/pack-studio", git_dir=upstream) == ""
    assert body["pull_request"] is None
    assert body["pr_error"]["code"] == "pr_permission_missing"
    expected = f"{server.base_url}/acme/packs/compare/main...anna:{branch}?expand=1"
    assert body["compare_url"] == expected
    assert body["git"]["workspace"]["fork_url"] == server.url("anna/packs.git")
    view = (await stand.client.get(f"{API}/workspaces/{ws_id}/git")).json()
    assert view["compare_url"] == expected


async def test__github__push_forbidden_without_api_answer__is_fork_required(
    stand: Stand, http_git_server_factory: Callable[..., GitHttpServer]
) -> None:
    server = http_git_server_factory()
    ws_id, _ = await _hosted_workspace(stand, server, "github")
    server.mode = "push_403"

    resp = await stand.client.post(f"{API}/workspaces/{ws_id}/git/propose", json={})

    assert resp.status_code == 409, resp.text
    assert resp.json()["code"] == "fork_required"


def _push_option_hook(bare: Path, log: Path) -> None:
    hook = bare / "hooks" / "post-receive"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text(
        "#!/bin/sh\n"
        "i=0\n"
        'while [ "$i" -lt "${GIT_PUSH_OPTION_COUNT:-0}" ]; do\n'
        f'  eval "printf \'%s\\\\n\' \\"\\$GIT_PUSH_OPTION_$i\\"" >> {log}\n'
        "  i=$((i+1))\n"
        "done\n"
        'echo "View merge request for branch:"\n'
        'echo "  https://gitlab.example.org/fcs/packs/-/merge_requests/7"\n',
        encoding="utf-8",
    )
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


async def test__gitlab__merge_request_via_push_options_and_pipeline_needs_read_api(
    stand: Stand, http_git_server_factory: Callable[..., GitHttpServer]
) -> None:
    server = http_git_server_factory()
    ws_id, bare = await _hosted_workspace(stand, server, "gitlab", "fcs/packs.git")
    run_git("config", "receive.advertisePushOptions", "true", git_dir=bare)
    log = stand.root / "push-options.txt"
    _push_option_hook(bare, log)
    server.api["/api/v4/projects/fcs%2Fpacks/pipelines"] = _reply(403, {"message": "insufficient_scope"})

    resp = await stand.client.post(f"{API}/workspaces/{ws_id}/git/propose", json={"title": "fix(packs): MR"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pull_request"] == {
        "number": 7,
        "url": "https://gitlab.example.org/fcs/packs/-/merge_requests/7",
        "created": True,
    }
    options = log.read_text(encoding="utf-8").splitlines()
    assert "merge_request.create" in options
    assert "merge_request.target=main" in options
    assert "merge_request.title=fix(packs): MR" in options
    assert any(o.startswith("merge_request.description=") and "Студии шаблонов" in o for o in options)
    checks = (await stand.client.get(f"{API}/workspaces/{ws_id}/git/checks")).json()
    assert checks["available"] is False
    assert checks["reason"] == "ci_status_unavailable"
    assert (
        checks["web_url"] == f"{server.base_url}/fcs/packs/-/pipelines?ref={body['git']['branch'].replace('/', '%2F')}"
    )
    (pipelines,) = _api_requests(server, "/api/v4/projects/fcs%2Fpacks/pipelines")
    assert pipelines.headers.get("private-token") == server.token
