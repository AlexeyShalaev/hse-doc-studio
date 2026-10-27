from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from fastapi import APIRouter, Depends, FastAPI
from hse_doc_studio.api import guards
from hse_doc_studio.api.guards import project_access_guard
from hse_doc_studio.core.access.context import current_actor, set_current_actor
from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.integration.api.vcs.conftest import FAKE_PROJECT_ID, create_project

_STRANGER = Actor.user("stranger")
_OWNER = Actor.user("owner")
_OWNER_ACL_GRANTS = {"owner": Grant(role=Role.owner)}


def _base(project: dict[str, Any]) -> str:
    return f"/api/v1/projects/{project['id']}"


def _make_read_only(project: dict[str, Any]) -> None:
    project_json = Path(project["folder"]) / ".hse-studio" / "project.json"
    data = json.loads(project_json.read_text(encoding="utf-8"))
    data["schema"] = {"version": 7, "read_compat": 1, "write_compat": 7, "written_by": "9.0.0"}
    project_json.write_text(json.dumps(data), encoding="utf-8")


def _stub_server(monkeypatch: pytest.MonkeyPatch, actor: Actor, grants: dict[str, Grant] | None = None) -> None:
    async def resolve(_request: object) -> Actor:
        return actor

    async def load_acl(_request: object, project_id: str) -> ProjectAcl | None:
        if grants is None:
            return None
        return ProjectAcl(project_id=project_id, owner_id="owner", grants=grants)

    monkeypatch.setattr(guards, "resolve_actor", resolve)
    monkeypatch.setattr(guards, "load_project_acl", load_acl)


@pytest_asyncio.fixture
async def guarded_app(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    container = create_test_container(tmp_path / "data")
    async with AsyncClient(transport=ASGITransport(app=create_test_app(container)), base_url="http://test") as client:
        yield client
    await container.close()


@pytest_asyncio.fixture
async def project(guarded_app: AsyncClient, tmp_path: Path) -> dict[str, Any]:
    return await create_project(guarded_app, tmp_path / "proj")


async def test__guard__local_actor__existing_routes_unchanged(
    guarded_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def forbidden(*_args: object) -> ProjectAcl | None:
        raise AssertionError("the local actor must not load the project membership")

    monkeypatch.setattr(guards, "load_project_acl", forbidden)
    base = _base(project)

    assert (await guarded_app.get(base)).status_code == 200
    assert (await guarded_app.put(f"{base}/files/notes/a.txt", content=b"x")).status_code in {200, 204}
    assert (await guarded_app.post(f"{base}/vcs/snapshots", json={"message": "m"})).status_code in {200, 201}
    assert (await guarded_app.patch(base, json={"name": "Новое имя"})).status_code == 200
    assert (await guarded_app.get(f"/api/v1/projects/{FAKE_PROJECT_ID}")).status_code == 404
    assert (await guarded_app.delete(base)).status_code == 204


async def test__guard__local_actor__read_only_project_still_locked_except_restore_and_delete(
    guarded_app: AsyncClient, project: dict[str, Any]
) -> None:
    _make_read_only(project)
    base = _base(project)

    assert (await guarded_app.patch(base, json={"name": "Другое"})).status_code == 423
    assert (await guarded_app.post(f"{base}/vcs/restore", json={"commit_id": "0" * 40})).status_code != 423
    assert (await guarded_app.delete(base)).status_code == 204


async def test__guard__read_only_project__file_path_ending_like_an_exempt_route_is_still_locked(
    guarded_app: AsyncClient, project: dict[str, Any]
) -> None:
    _make_read_only(project)
    base = _base(project)

    for tail in ("a/git/fetch", "notes/git/ci/preview", "x/vcs/restore", f"projects/{project['id']}"):
        assert (await guarded_app.put(f"{base}/files/{tail}", content=b"x")).status_code == 423, tail
        assert (await guarded_app.delete(f"{base}/files/{tail}")).status_code == 423, tail
    assert (await guarded_app.post(f"{base}/git/fetch")).status_code != 423
    assert (await guarded_app.post(f"{base}/git/ci/preview", json={})).status_code != 423


async def test__guard__stub_non_local_user_without_grant__404_before_423(
    guarded_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_read_only(project)
    _stub_server(monkeypatch, _STRANGER)

    resp = await guarded_app.patch(_base(project), json={"name": "Чужое"})

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Project not found"}


async def test__guard__stub_non_local_owner__reaches_write_guard(
    guarded_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_read_only(project)
    _stub_server(monkeypatch, _OWNER, _OWNER_ACL_GRANTS)

    assert (await guarded_app.patch(_base(project), json={"name": "Моё"})).status_code == 423


async def test__guard__stub_non_local_reader__member_with_too_little_role_gets_403(
    guarded_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_server(monkeypatch, Actor.user("reader"), {"reader": Grant(role=Role.reader)})
    base = _base(project)

    assert (await guarded_app.get(base)).status_code == 200
    assert (await guarded_app.patch(base, json={"name": "Не моё"})).status_code == 403
    assert (await guarded_app.get(f"{base}/files", params={"path": "."})).status_code == 403


async def test__guard__non_local_project_route_without_rule__denied(monkeypatch: pytest.MonkeyPatch) -> None:
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(project_access_guard)])

    @router.get("/unlisted/{project_id}")
    async def unlisted(project_id: str) -> dict[str, str]:
        return {"project_id": project_id}

    @router.get("/open-route")
    async def open_route() -> dict[str, bool]:
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)
    _stub_server(monkeypatch, _OWNER, _OWNER_ACL_GRANTS)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/unlisted/abc")).status_code == 403
        assert (await client.get("/api/v1/open-route")).status_code == 200

    monkeypatch.undo()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/unlisted/abc")).status_code == 200


async def test__guard__sets_current_actor_inside_endpoint_task_and_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(project_access_guard)])

    @router.get("/probe")
    async def probe() -> dict[str, str | None]:
        in_task = current_actor()
        in_thread = await asyncio.to_thread(current_actor)
        in_child = await asyncio.create_task(_read_actor())
        return {"task": in_task and in_task.kind, "thread": in_thread and in_thread.kind, "child": in_child}

    async def _read_actor() -> str | None:
        actor = current_actor()
        return actor and actor.kind

    app = FastAPI()
    app.include_router(router)
    set_current_actor(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/probe")

    assert resp.json() == {"task": "local", "thread": "local", "child": "local"}


async def test__guard__office_callback_reachable_for_non_local(
    guarded_app: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_server(monkeypatch, _STRANGER)

    resp = await guarded_app.post(
        "/api/v1/office-editor/callback",
        params={"project_id": project["id"], "doc_id": "report", "sig": "x"},
        json=[],
    )

    assert resp.status_code == 400
    assert resp.json() == {"detail": "callback body must be a JSON object"}
