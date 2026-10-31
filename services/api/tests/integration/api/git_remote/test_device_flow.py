"""Вход устройства по коду: устройство начинает, человек на /device подтверждает сессией, токен выдаётся один раз."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.api.git_remote.conftest import Live, Person, git

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]


def _start(live: Live, scopes: list[str] | None = None) -> dict[str, Any]:
    body = {
        "client_name": "Студия на MacBook Анны",
        "client_kind": "desktop",
        "scopes": scopes or ["git:read", "git:write"],
    }
    response = live.call("POST", "/api/v1/auth/device/code", json=body)
    assert response.status_code == 200, response.text
    return dict(response.json())


def _session(live: Live, person: Person, method: str, path: str, **kwargs: Any) -> Any:
    with live.client() as client:
        return client.request(method, path, headers=person.session, cookies=person.cookies, **kwargs)


def _poll(live: Live, device_code: str) -> Any:
    return live.call("POST", "/api/v1/auth/device/token", json={"device_code": device_code})


def test__device_flow__approve_delivers_git_token_once(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    started = _start(live)
    code = started["user_code"]
    assert started["verification_uri"] == f"{live.base}/device"
    assert started["verification_uri_complete"] == f"{live.base}/device?code={code}"
    assert (started["expires_in"], started["interval"]) == (600, 5)
    assert _poll(live, started["device_code"]).json() == {"error": "authorization_pending"}

    info = _session(live, anna, "GET", f"/api/v1/account/device/{code.lower()}")
    assert info.status_code == 200, info.text
    assert (info.json()["client_name"], info.json()["status"]) == ("Студия на MacBook Анны", "pending")
    approved = _session(
        live, anna, "POST", f"/api/v1/account/device/{code}", json={"decision": "approve", "scopes": ["git:read"]}
    )
    assert approved.json()["status"] == "approved"
    assert approved.json()["granted_scopes"] == ["git:read"]

    import time

    time.sleep(5)
    token = _poll(live, started["device_code"])
    assert token.status_code == 200, token.text
    body = token.json()
    assert (body["token_type"], body["scope"], body["expires_in"]) == ("bearer", "git:read", 7776000)
    time.sleep(5)
    assert _poll(live, started["device_code"]).json() == {"error": "expired_token"}
    assert "refs/heads/master" in git("ls-remote", live.repo_url(project, body["access_token"]), cwd=live.tmp).stdout
    tokens = _session(live, anna, "GET", "/api/v1/account/tokens").json()
    device = [t for t in tokens if t["origin"] == "device"]
    assert [(t["client_name"], t["client_kind"], t["scopes"]) for t in device] == [
        ("Студия на MacBook Анны", "desktop", ["git:read"])
    ]
    again = _session(live, anna, "POST", f"/api/v1/account/device/{code}", json={"decision": "deny", "scopes": []})
    assert (again.status_code, again.json()["code"]) == (409, "device_code_used")


def test__device_flow__deny_slow_down_pat_and_foreign(live: Live) -> None:
    anna, boris = live.person("anna"), live.person("boris")
    started = _start(live)
    code = started["user_code"]
    assert _poll(live, started["device_code"]).json() == {"error": "authorization_pending"}
    assert _poll(live, started["device_code"]).json() == {"error": "slow_down"}

    by_pat = live.call("POST", f"/api/v1/account/device/{code}", anna, json={"decision": "approve", "scopes": []})
    assert by_pat.status_code == 403
    denied = _session(live, anna, "POST", f"/api/v1/account/device/{code}", json={"decision": "deny", "scopes": []})
    assert denied.json()["status"] == "denied"
    import time

    time.sleep(5)
    assert _poll(live, started["device_code"]).json() == {"error": "access_denied"}
    foreign = _session(live, boris, "GET", f"/api/v1/account/device/{code}")
    assert (foreign.status_code, foreign.json()["code"]) == (404, "device_code_invalid")
    assert _poll(live, "hsdv_unknown").json() == {"error": "expired_token"}


def test__device_flow__invalid_scopes(live: Live) -> None:
    anna = live.person("anna")
    bad = live.call(
        "POST", "/api/v1/auth/device/code", json={"client_name": "x", "client_kind": "cli", "scopes": ["api"]}
    )
    assert bad.status_code == 422
    started = _start(live, ["git:read"])
    widened = _session(
        live,
        anna,
        "POST",
        f"/api/v1/account/device/{started['user_code']}",
        json={"decision": "approve", "scopes": ["git:read", "git:write"]},
    )
    assert (widened.status_code, widened.json()["code"]) == (422, "device_scope_invalid")
