"""Выборка по git по HTTPS: настоящий `git clone` и `git fetch` против живого сервера Студии."""

from __future__ import annotations

import base64

import pytest

from tests.integration.api.git_remote.conftest import Live, git

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]


def test__clone__owner_with_git_token__gets_project_files(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    token = live.token(anna, ["git:read"])

    git("clone", live.repo_url(project, token), "work", cwd=live.tmp)

    work = live.tmp / "work"
    assert (work / ".hse-studio" / "project.json").is_file()
    assert not (work / ".hse-studio" / "git").exists()
    refs = git("ls-remote", live.repo_url(project, token), cwd=live.tmp).stdout
    assert "refs/heads/master" in refs
    assert "refs/hse" not in refs
    assert "refs/tags" not in refs


def test__clone__bearer_header_and_protocol_v0__work(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    token = live.token(anna, ["git:read", "git:write"])

    git(
        "-c",
        f"http.extraHeader=Authorization: Bearer {token}",
        "-c",
        "protocol.version=0",
        "clone",
        live.repo_url(project),
        "work",
        cwd=live.tmp,
    )

    assert (live.tmp / "work" / ".hse-studio" / "project.json").is_file()


def test__fetch__denied_cases(live: Live) -> None:
    anna, boris, vera = live.person("anna"), live.person("boris"), live.person("vera")
    project = live.create_project(anna)
    live.add_member(project, vera, "reader", show_sources=False)
    api_only = live.token(anna, ["api"])

    no_token = live.call("GET", f"/git/{project}.git/info/refs?service=git-upload-pack")
    assert no_token.status_code == 401
    assert no_token.headers["www-authenticate"] == 'Basic realm="HSE Doc Studio"'
    assert "git" in no_token.text
    basic = base64.b64encode(f"x:{api_only}".encode()).decode()
    scope = live.call(
        "GET", f"/git/{project}.git/info/refs?service=git-upload-pack", headers={"Authorization": f"Basic {basic}"}
    )
    assert scope.status_code == 403
    stranger = git("ls-remote", live.repo_url(project, live.token(boris, ["git:read"])), cwd=live.tmp, check=False)
    assert stranger.returncode != 0
    assert "not found" in stranger.stderr.lower()
    reader = git("ls-remote", live.repo_url(project, live.token(vera, ["git:read"])), cwd=live.tmp, check=False)
    assert reader.returncode != 0
    assert "403" in reader.stderr or "нет права" in reader.stderr or "may not" in reader.stderr
    cookie_only = live.call(
        "GET", f"/git/{project}.git/info/refs?service=git-upload-pack", cookies=anna.cookies, headers=anna.session
    )
    assert cookie_only.status_code == 401


def test__fetch__reader_with_sources_clones_dumb_protocol_refused_bad_id_404(live: Live) -> None:
    anna, vera = live.person("anna"), live.person("vera")
    project = live.create_project(anna)
    live.add_member(project, vera, "reader", show_sources=True)
    token = live.token(vera, ["git:read"])

    git("clone", live.repo_url(project, token), "work", cwd=live.tmp)
    dumb = live.call("GET", f"/git/{project}.git/info/refs", headers={"Authorization": f"Bearer {token}"})
    assert dumb.status_code == 403
    assert "2.31" in dumb.text
    bad = live.call(
        "GET", "/git/not-a-uuid.git/info/refs?service=git-upload-pack", headers={"Authorization": f"Bearer {token}"}
    )
    assert bad.status_code == 404


def test__info_and_whoami(live: Live) -> None:
    anna = live.person("anna")
    token = live.token(anna, ["git:read", "git:write"], name="Студия на MacBook")

    info = live.call("GET", "/git/-/info").json()
    assert info["server"] == "hse-doc-studio"
    assert info["device_flow"] is True
    who = live.call("GET", "/git/-/whoami", headers={"Authorization": f"Bearer {token}"})
    assert who.status_code == 200, who.text
    body = who.json()
    assert body["user"]["id"] == anna.id
    assert body["scopes"] == ["git:read", "git:write"]
    assert body["token"]["name"] == "Студия на MacBook"
    assert live.call("GET", "/git/-/whoami").status_code == 401
