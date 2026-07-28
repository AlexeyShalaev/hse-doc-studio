from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pytest_lazy_fixtures import lf

from tests.integration.api.vcs.conftest import FAKE_PROJECT_ID, edit_tracked_file


def _edit_annotation(project: dict[str, Any], marker: str) -> None:
    path = Path(project["folder"]) / "annotation" / "annotation.tex"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n% {marker}\n")


async def _snapshot(client: AsyncClient, project_id: str, message: str) -> dict[str, Any]:
    resp = await client.post(f"/api/v1/projects/{project_id}/vcs/snapshots", json={"message": message})
    assert resp.status_code == 200, resp.text
    commit = resp.json()
    assert commit is not None
    return commit


async def test__api__list_vcs_history__fresh_project__contains_root_snapshot(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    resp = await test_app.get(f"/api/v1/projects/{project['id']}/vcs/history")

    assert resp.status_code == 200, resp.text
    history = resp.json()
    assert len(history) == 1
    assert history[0]["kind"] == "init"


async def test__api__list_vcs_history__filters_by_doc_id(test_app: AsyncClient, project: dict[str, Any]) -> None:
    project_id = project["id"]
    _edit_annotation(project, "annotation change")
    annotation_commit = await _snapshot(test_app, project_id, "annotation change")
    edit_tracked_file(project, "thesis change")
    thesis_commit = await _snapshot(test_app, project_id, "thesis change")

    resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/history", params={"doc_id": "thesis"})

    assert resp.status_code == 200, resp.text
    ids = [c["id"] for c in resp.json()]
    assert thesis_commit["id"] in ids
    assert annotation_commit["id"] not in ids


async def test__api__list_vcs_history__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/history")

    assert resp.status_code == 404


async def test__api__get_vcs_commit__returns_detail_with_file_changes(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    edit_tracked_file(project, "detail me")
    commit = await _snapshot(test_app, project_id, "detail me")

    resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/commits/{commit['id']}")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["commit"]["id"] == commit["id"]
    assert data["commit"]["stats"]["files"] == 1
    assert any(f["path"] == "thesis/thesis.tex" and f["change"] == "M" for f in data["files"])


@pytest_asyncio.fixture
async def existing_project_id(project: dict[str, Any]) -> str:
    return project["id"]


@pytest.mark.parametrize(
    ("project_id", "commit_id"),
    [
        pytest.param(lf("existing_project_id"), "deadbeefdeadbeef", id="unknown_commit_id"),
        pytest.param(FAKE_PROJECT_ID, "abc123", id="nonexistent_project"),
    ],
)
async def test__api__get_vcs_commit__invalid_target__returns_404(
    test_app: AsyncClient, project_id: str, commit_id: str
) -> None:
    # A genuine inconsistency in the router: VcsCommandError → 400 everywhere
    # else, but get_vcs_commit maps it to 404 instead. Documented, not fixed here.
    resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/commits/{commit_id}")

    assert resp.status_code == 404


async def test__api__get_vcs_diff__no_range__shows_uncommitted_change(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    edit_tracked_file(project, "diff me uncommitted")

    resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/diff")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["files"]) == 1
    file_diff = data["files"][0]
    assert file_diff["path"] == "thesis/thesis.tex"
    assert file_diff["change"] == "M"
    assert "diff me uncommitted" in file_diff["patch"]
    assert file_diff["binary"] is False


async def test__api__get_vcs_diff__between_two_commits__shows_the_real_change(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    edit_tracked_file(project, "first change")
    commit_a = await _snapshot(test_app, project_id, "first change")
    edit_tracked_file(project, "second change")
    commit_b = await _snapshot(test_app, project_id, "second change")

    resp = await test_app.get(
        f"/api/v1/projects/{project_id}/vcs/diff",
        params={"from_id": commit_a["id"], "to_id": commit_b["id"]},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["from_id"] == commit_a["id"]
    assert data["to_id"] == commit_b["id"]
    assert len(data["files"]) == 1
    patch = data["files"][0]["patch"]
    assert "+% second change" in patch
    # The first change already landed in commit_a — it may still show up as
    # unchanged *context* around the hunk, but must not be part of this diff's
    # additions.
    assert "+% first change" not in patch


async def test__api__get_vcs_diff__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/diff")

    assert resp.status_code == 404
