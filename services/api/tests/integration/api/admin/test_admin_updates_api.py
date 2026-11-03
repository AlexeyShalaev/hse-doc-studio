"""`/api/admin/updates` и `/api/updater/v1`: права, формы, токен апдейтера, полный круг «запрос -> опрос -> событие»."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers import updater_api
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.server_update.entities import ReleaseInfo
from hse_doc_studio.core.server_update.options import UpdateOptions
from hse_doc_studio.core.server_update.protocols import FeedAnswer
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.server_update.admin import UpdateAdmin
from hse_doc_studio.use_cases.server_update.service import UpdateService
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from tests.fakes.auth import empty_bearer_resolver
from tests.fakes.backup import Admins, InMemoryDestinations, InMemoryRuns, RecordingNotifier
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.ops import NoopUow
from tests.fakes.server_update import FakeBackupStarter, InMemoryUpdateRuns, StaticSource
from tests.integration.api.admin.test_admin_users_api import _Env as _UsersEnv

TOKEN = "updater-secret-token"  # noqa: S105
_ID = "00000000-0000-0000-0000-000000000001"
RELEASES = (ReleaseInfo("0.5.0", "2026-11-03", ("Автообновление",), "https://example.org/d.json"), ReleaseInfo("0.4.0"))


class _Stack:
    def __init__(self, users: _UsersEnv) -> None:
        self.users = users
        self.runs = InMemoryUpdateRuns()
        self.settings = InMemoryInstanceSettingsRepository()
        backup_runs = InMemoryRuns()
        self.service = UpdateService(
            self.runs,
            self.settings,
            StaticSource(FeedAnswer(releases=RELEASES, checked=True)),
            FakeBackupStarter(backup_runs),
            backup_runs,
            InMemoryDestinations(),
            users.audit,
            RecordingNotifier(),  # type: ignore[arg-type]
            Admins("boss"),
            NoopUow(),  # type: ignore[arg-type]
            UpdateOptions(current_version="0.4.0", executor_enabled=True),
            lambda: datetime(2026, 11, 3, 3, 0, tzinfo=UTC),
        )
        self.client: AsyncClient


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, s: _Stack) -> None:
        super().__init__()
        self.s = s

    @provide
    def resolver(self) -> IActorResolver:
        from hse_doc_studio.use_cases.identity.sessions import SessionService  # noqa: PLC0415

        return ChainActorResolver(
            [SessionCookieResolver(SessionService(self.s.users.sessions, self.s.users.users)), empty_bearer_resolver()]
        )

    @provide
    def admin(self) -> UpdateAdmin:
        return UpdateAdmin(self.s.service)

    @provide
    def service(self) -> UpdateService:
        return self.s.service


@pytest_asyncio.fixture
async def stack(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Stack]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    monkeypatch.setattr(settings.server_update, "updater_token", SecretStr(TOKEN))
    s = _Stack(_UsersEnv())
    app = FastAPI()
    app.include_router(make_admin_router())
    app.include_router(updater_api.router)
    install_exception_handlers(app)
    container = make_async_container(_Provider(s), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 5000)), base_url="http://test") as c:
        s.client = c
        yield s
    await container.close()


_BODY = {
    "policy": "auto",
    "channel": "stable",
    "max_bump": "minor",
    "window_days": [0, 1, 2, 3, 4, 5, 6],
    "window_start_min": 0,
    "window_minutes": 1440,
    "backup_first": False,
    "verify": "digest",
    "notify_admins": True,
}
_ROUTES: list[tuple[str, str, Any]] = [
    ("GET", "/api/admin/updates/status", None),
    ("PUT", "/api/admin/updates/settings", _BODY),
    ("POST", "/api/admin/updates/check", None),
    ("POST", "/api/admin/updates/runs", {}),
    ("POST", "/api/admin/updates/rollback", {}),
    ("POST", f"/api/admin/updates/runs/{_ID}/cancel", None),
    ("GET", "/api/admin/updates/runs", None),
    ("GET", f"/api/admin/updates/runs/{_ID}", None),
]


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES, ids=[f"{m} {p[18:50]}" for m, p, _ in _ROUTES])
async def test__routes__student_404_anonymous_401(stack: _Stack, method: str, path: str, body: Any) -> None:
    student = await stack.users.add("student")
    assert (await stack.client.request(method, path, json=body, headers=student)).status_code == 404
    assert (await stack.client.request(method, path, json=body)).status_code == 401
    assert stack.runs.items == {}


async def test__full_circle__settings_check_start_poll_events_rollback_guard(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    updater = {"Authorization": f"Bearer {TOKEN}"}

    saved = await c.put("/api/admin/updates/settings", json=_BODY, headers=boss)
    assert saved.status_code == 200
    assert saved.json()["settings"]["policy"] == "auto"
    checked = (await c.post("/api/admin/updates/check", headers=boss)).json()
    assert checked["available"]["version"] == "0.5.0"
    assert checked["available"]["has_digest"] is True
    assert checked["executor"] == "compose"
    assert checked["updater_online"] is False

    offline = await c.post("/api/admin/updates/runs", json={}, headers=boss)
    assert (offline.status_code, offline.json()["code"]) == (409, "updater_offline")

    assert (
        await c.post("/api/updater/v1/poll", json={"updater_version": "0.4.0", "busy": True}, headers=updater)
    ).json() == {"run": None}
    started = await c.post("/api/admin/updates/runs", json={}, headers=boss)
    assert started.status_code == 202
    assert started.json()["status"] == "queued"
    run_id = started.json()["id"]

    spec = (await c.post("/api/updater/v1/poll", json={"updater_version": "0.4.0"}, headers=updater)).json()["run"]
    assert spec["run_id"] == run_id
    assert spec["to_version"] == "0.5.0"
    assert spec["verify"] == "digest"
    assert spec["digests_url"] == "https://example.org/d.json"

    def event(seq: int, **kw: Any) -> dict[str, Any]:
        return {"seq": seq, "at": "2026-11-03T03:01:00+00:00", "phase": "pull", "message": "m", **kw}

    first = await c.post(f"/api/updater/v1/runs/{run_id}/events", json=event(1), headers=updater)
    assert first.json() == {"status": "running", "last_seq": 1}
    replay = await c.post(f"/api/updater/v1/runs/{run_id}/events", json=event(1, message="dup"), headers=updater)
    assert replay.json()["last_seq"] == 1
    done = await c.post(
        f"/api/updater/v1/runs/{run_id}/events",
        json=event(2, phase="finish", status="succeeded", from_revision="r1", to_revision="r2"),
        headers=updater,
    )
    assert done.json()["status"] == "succeeded"

    detail = (await c.get(f"/api/admin/updates/runs/{run_id}", headers=boss)).json()
    assert detail["status"] == "succeeded"
    assert (detail["from_revision"], detail["to_revision"]) == ("r1", "r2")
    assert [e["seq"] for e in detail["events"] if e["seq"]] == [1, 2]
    page = (await c.get("/api/admin/updates/runs?limit=5", headers=boss)).json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == run_id
    actions = [e.action for e in await stack.users.audit.list()]
    assert {"update.settings_update", "update.check", "update.run_request", "update.run_finish"} <= set(actions)


async def test__rollback_requires_confirmation_when_the_schema_moved(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    updater = {"Authorization": f"Bearer {TOKEN}"}
    await c.put("/api/admin/updates/settings", json=_BODY, headers=boss)
    await c.post("/api/admin/updates/check", headers=boss)
    await c.post("/api/updater/v1/poll", json={"busy": True}, headers=updater)
    run_id = (await c.post("/api/admin/updates/runs", json={}, headers=boss)).json()["id"]
    await c.post("/api/updater/v1/poll", json={}, headers=updater)
    body = {
        "seq": 1,
        "at": "2026-11-03T03:05:00+00:00",
        "phase": "finish",
        "status": "succeeded",
        "from_revision": "r1",
        "to_revision": "r2",
    }
    await c.post(f"/api/updater/v1/runs/{run_id}/events", json=body, headers=updater)
    # версия приложения теперь равна целевой: подменяем параметры процесса
    stack.service._options = UpdateOptions(current_version="0.5.0", executor_enabled=True)  # noqa: SLF001

    status = (await c.get("/api/admin/updates/status", headers=boss)).json()
    assert (status["rollback_version"], status["rollback_needs_restore"]) == ("0.4.0", True)
    refused = await c.post("/api/admin/updates/rollback", json={}, headers=boss)
    assert (refused.status_code, refused.json()["field"]) == (422, "restore_db")
    accepted = await c.post("/api/admin/updates/rollback", json={"restore_db": True}, headers=boss)
    assert accepted.status_code == 202
    assert accepted.json()["kind"] == "rollback"


@pytest.mark.parametrize("auth", [None, "Bearer nope", "Basic abc", f"Bearer {TOKEN}x"])
async def test__updater_api__rejects_missing_and_wrong_tokens(stack: _Stack, auth: str | None) -> None:
    headers = {"Authorization": auth} if auth else {}
    r = await stack.client.post("/api/updater/v1/poll", json={}, headers=headers)
    assert (r.status_code, r.json()["code"]) == (401, "unauthorized")
    e = await stack.client.post(
        f"/api/updater/v1/runs/{_ID}/events",
        json={"seq": 1, "at": "2026-11-03T03:05:00+00:00", "phase": "x"},
        headers=headers,
    )
    assert e.status_code == 401


async def test__updater_api__is_closed_when_no_token_is_configured(
    stack: _Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.server_update, "updater_token", SecretStr(""))
    r = await stack.client.post("/api/updater/v1/poll", json={}, headers={"Authorization": "Bearer "})
    assert r.status_code == 401


async def test__settings__invalid_window_is_a_422_with_the_field(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    r = await stack.client.put("/api/admin/updates/settings", json={**_BODY, "window_minutes": 5}, headers=boss)
    assert r.status_code == 422


async def test__kubernetes__risk_gate_run_and_needs_manual_action_over_http(stack: _Stack) -> None:
    stack.service._options = UpdateOptions(  # noqa: SLF001
        current_version="0.4.0", executor_enabled=True, executor="kubernetes"
    )
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    updater = {"Authorization": f"Bearer {TOKEN}"}
    await c.put("/api/admin/updates/settings", json={**_BODY, "backup_first": True}, headers=boss)
    await c.post("/api/admin/updates/check", headers=boss)
    await c.post("/api/updater/v1/poll", json={"busy": True}, headers=updater)

    status = (await c.get("/api/admin/updates/status", headers=boss)).json()
    assert (status["executor"], status["risk_confirmation_required"]) == ("kubernetes", True)
    refused = await c.post("/api/admin/updates/runs", json={}, headers=boss)
    assert (refused.status_code, refused.json()["code"], refused.json()["field"]) == (
        422,
        "risk_not_confirmed",
        "accept_risk",
    )

    started = await c.post("/api/admin/updates/runs", json={"accept_risk": True}, headers=boss)
    assert started.status_code == 202
    run_id = started.json()["id"]
    await c.post("/api/updater/v1/poll", json={}, headers=updater)
    stuck = {
        "seq": 1,
        "at": "2026-11-03T03:05:00+00:00",
        "phase": "finish",
        "level": "error",
        "status": "failed",
        "error_code": "needs_manual_action",
        "message": "Manual action is needed",
        "from_revision": "r1",
        "to_revision": "r2",
    }
    await c.post(f"/api/updater/v1/runs/{run_id}/events", json=stuck, headers=updater)

    detail = (await c.get(f"/api/admin/updates/runs/{run_id}", headers=boss)).json()
    assert (detail["status"], detail["error_code"], detail["db_restored"]) == ("failed", "needs_manual_action", False)
    audit = [e for e in await stack.users.audit.list() if e.action == "update.run_request"]
    assert audit[0].details["risk_accepted"] is True


async def test__kubernetes__rollback_after_schema_change_is_refused_with_409(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    updater = {"Authorization": f"Bearer {TOKEN}"}
    stack.service._options = UpdateOptions(  # noqa: SLF001
        current_version="0.4.0", executor_enabled=True, executor="kubernetes"
    )
    await c.put("/api/admin/updates/settings", json=_BODY, headers=boss)
    await c.post("/api/admin/updates/check", headers=boss)
    await c.post("/api/updater/v1/poll", json={"busy": True}, headers=updater)
    run_id = (await c.post("/api/admin/updates/runs", json={"accept_risk": True}, headers=boss)).json()["id"]
    await c.post("/api/updater/v1/poll", json={}, headers=updater)
    done = {
        "seq": 1,
        "at": "2026-11-03T03:05:00+00:00",
        "phase": "finish",
        "status": "succeeded",
        "from_revision": "r1",
        "to_revision": "r2",
    }
    await c.post(f"/api/updater/v1/runs/{run_id}/events", json=done, headers=updater)
    stack.service._options = UpdateOptions(  # noqa: SLF001
        current_version="0.5.0", executor_enabled=True, executor="kubernetes"
    )

    status = (await c.get("/api/admin/updates/status", headers=boss)).json()
    assert (status["rollback_version"], status["rollback_blocked"]) == (None, True)
    refused = await c.post("/api/admin/updates/rollback", json={"restore_db": True}, headers=boss)
    assert (refused.status_code, refused.json()["code"]) == (409, "rollback_unsafe")
