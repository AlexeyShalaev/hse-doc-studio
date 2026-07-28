from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pytest_lazy_fixtures import lf

from tests.integration.api.vcs.conftest import FAKE_PROJECT_ID


async def _create_branch(client: AsyncClient, project_id: str, name: str, *, switch: bool = True) -> dict[str, Any]:
    resp = await client.post(f"/api/v1/projects/{project_id}/vcs/branches", json={"name": name, "switch": switch})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test__api__list_vcs_branches__fresh_project__has_one_protected_current_branch(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    resp = await test_app.get(f"/api/v1/projects/{project['id']}/vcs/branches")

    assert resp.status_code == 200, resp.text
    branches = resp.json()
    assert len(branches) == 1
    assert branches[0]["name"] == "master"
    assert branches[0]["is_current"] is True
    assert branches[0]["is_protected"] is True


async def test__api__list_vcs_branches__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/branches")

    assert resp.status_code == 404


async def test__api__create_vcs_branch__with_switch__becomes_current(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]

    branch = await _create_branch(test_app, project_id, "feature-x", switch=True)

    assert branch["name"] == "feature-x"
    assert branch["is_current"] is True
    assert branch["is_protected"] is False

    list_resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/branches")
    by_name = {b["name"]: b for b in list_resp.json()}
    assert by_name["feature-x"]["is_current"] is True
    assert by_name["master"]["is_current"] is False


async def test__api__create_vcs_branch__without_switch__current_branch_unchanged(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]

    branch = await _create_branch(test_app, project_id, "feature-y", switch=False)

    assert branch["is_current"] is False
    status_resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/status")
    assert status_resp.json()["current_branch"] == "master"


async def test__api__create_vcs_branch__duplicate_name__returns_400(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    await _create_branch(test_app, project_id, "dup-branch", switch=False)

    resp = await test_app.post(f"/api/v1/projects/{project_id}/vcs/branches", json={"name": "dup-branch"})

    assert resp.status_code == 400


async def test__api__create_vcs_branch__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.post(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/branches", json={"name": "x"})

    assert resp.status_code == 404


async def test__api__switch_vcs_branch__to_existing_branch__updates_status(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    await _create_branch(test_app, project_id, "feature-z", switch=True)

    resp = await test_app.post(f"/api/v1/projects/{project_id}/vcs/branches/switch", json={"name": "master"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["current_branch"] == "master"


async def test__api__switch_vcs_branch__unknown_branch__returns_400(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    resp = await test_app.post(f"/api/v1/projects/{project['id']}/vcs/branches/switch", json={"name": "no-such-branch"})

    assert resp.status_code == 400


async def test__api__switch_vcs_branch__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.post(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/branches/switch", json={"name": "master"})

    assert resp.status_code == 404


async def test__api__delete_vcs_branch__non_current_non_protected__succeeds(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    await _create_branch(test_app, project_id, "throwaway", switch=False)

    resp = await test_app.delete(f"/api/v1/projects/{project_id}/vcs/branches", params={"name": "throwaway"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True
    list_resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/branches")
    assert "throwaway" not in [b["name"] for b in list_resp.json()]


@pytest_asyncio.fixture
async def current_branch_name(test_app: AsyncClient, project: dict[str, Any]) -> str:
    """A branch that is switched to, so deleting it hits the "can't delete the
    current branch" guard."""
    name = "current-one"
    await _create_branch(test_app, project["id"], name, switch=True)
    return name


@pytest_asyncio.fixture
async def protected_branch_name_while_elsewhere(test_app: AsyncClient, project: dict[str, Any]) -> str:
    """Switches away from "master" first, so deleting it hits the "protected
    branch" guard rather than the "current branch" guard."""
    await _create_branch(test_app, project["id"], "elsewhere", switch=True)
    return "master"


@pytest.mark.parametrize(
    "branch_name",
    [
        pytest.param(lf("current_branch_name"), id="current_branch"),
        pytest.param(lf("protected_branch_name_while_elsewhere"), id="protected_main_branch_while_not_current"),
        pytest.param("ghost", id="unknown_name"),
    ],
)
async def test__api__delete_vcs_branch__invalid_target__returns_400(
    test_app: AsyncClient, project: dict[str, Any], branch_name: str
) -> None:
    resp = await test_app.delete(f"/api/v1/projects/{project['id']}/vcs/branches", params={"name": branch_name})

    assert resp.status_code == 400, resp.text


async def test__api__delete_vcs_branch__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.delete(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/branches", params={"name": "master"})

    assert resp.status_code == 404
