from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.integration.api.chat.conftest import create_project


async def test__api__create_chat__returns_session_with_title_and_doc(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id = await create_project(test_app, tmp_path / "proj")

    resp = await test_app.post(f"/api/v1/projects/{project_id}/chats", json={"title": "My chat", "doc_id": "thesis"})

    assert resp.status_code == 201, resp.text
    assert resp.json()["title"] == "My chat"
    assert resp.json()["doc_id"] == "thesis"


async def test__api__list_chats__after_create__includes_it_not_running(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id = await create_project(test_app, tmp_path / "proj")
    created = (await test_app.post(f"/api/v1/projects/{project_id}/chats", json={"title": "t"})).json()

    resp = await test_app.get(f"/api/v1/projects/{project_id}/chats")

    assert resp.status_code == 200, resp.text
    assert [s["id"] for s in resp.json()] == [created["id"]]
    assert resp.json()[0]["is_running"] is False


async def test__api__get_chat__returns_detail_with_empty_messages_and_no_active_run(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id = await create_project(test_app, tmp_path / "proj")
    created = (await test_app.post(f"/api/v1/projects/{project_id}/chats", json={"title": "t"})).json()

    resp = await test_app.get(f"/api/v1/projects/{project_id}/chats/{created['id']}")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["messages"] == []
    assert data["active_run_id"] is None


async def test__api__get_chat__unknown_session__404(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id = await create_project(test_app, tmp_path / "proj")
    fake_session_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.get(f"/api/v1/projects/{project_id}/chats/{fake_session_id}")

    assert resp.status_code == 404


async def test__api__rename_chat__updates_title(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id = await create_project(test_app, tmp_path / "proj")
    created = (await test_app.post(f"/api/v1/projects/{project_id}/chats", json={"title": "old"})).json()

    resp = await test_app.patch(f"/api/v1/projects/{project_id}/chats/{created['id']}", json={"title": "new"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "new"


async def test__api__delete_chat__removes_it_from_list(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id = await create_project(test_app, tmp_path / "proj")
    created = (await test_app.post(f"/api/v1/projects/{project_id}/chats", json={"title": "t"})).json()

    resp = await test_app.delete(f"/api/v1/projects/{project_id}/chats/{created['id']}")

    assert resp.status_code == 204, resp.text
    listed = await test_app.get(f"/api/v1/projects/{project_id}/chats")
    assert listed.json() == []
