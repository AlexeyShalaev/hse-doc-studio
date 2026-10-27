from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas.git_sync import ProfileResponse, ProfileValidationError
from httpx import AsyncClient

from tests.integration.api.vcs.conftest import create_project, edit_tracked_file

_PROFILE = {"name": "Алиса Иванова", "email": "Alice@Example.org"}


async def test__api__get_profile__fresh_install__is_default_with_bot_signature(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/profile")

    assert resp.status_code == 200, resp.text
    body = ProfileResponse.model_validate(resp.json())
    assert body.name is None
    assert body.email is None
    assert body.is_default is True
    assert body.commit_preview == f"{body.effective_name} <{body.effective_email}>"
    assert body.effective_email == "bot@hse-studio.local"


async def test__api__put_profile__valid__returns_effective_profile_and_persists(test_app: AsyncClient) -> None:
    resp = await test_app.put("/api/v1/profile", json=_PROFILE)

    assert resp.status_code == 200, resp.text
    body = ProfileResponse.model_validate(resp.json())
    assert (body.name, body.email) == ("Алиса Иванова", "Alice@example.org")
    assert (body.effective_name, body.effective_email) == ("Алиса Иванова", "Alice@example.org")
    assert body.is_default is False
    assert body.commit_preview == "Алиса Иванова <Alice@example.org>"
    again = await test_app.get("/api/v1/profile")
    assert again.json() == resp.json()


async def test__api__put_profile__invalid__returns_422_with_code_per_field(test_app: AsyncClient) -> None:
    resp = await test_app.put("/api/v1/profile", json={"name": "Eve <x>", "email": "alice@localhost"})

    assert resp.status_code == 422, resp.text
    body = ProfileValidationError.model_validate(resp.json())
    assert [(e.loc, e.code) for e in body.detail] == [
        (["body", "name"], "name_invalid"),
        (["body", "email"], "email_invalid"),
    ]
    assert (await test_app.get("/api/v1/profile")).json()["is_default"] is True


async def test__api__put_profile__interface_language_en__message_is_english(test_app: AsyncClient) -> None:
    resp = await test_app.put(
        "/api/v1/profile",
        json={"name": "Alice", "email": "nope"},
        headers={"X-Interface-Language": "en"},
    )

    assert resp.status_code == 422
    assert resp.json()["detail"][0]["msg"] == "Enter an address like name@example.com."


async def test__api__delete_profile__returns_default_and_forgets_values(test_app: AsyncClient) -> None:
    await test_app.put("/api/v1/profile", json=_PROFILE)

    resp = await test_app.delete("/api/v1/profile")

    assert resp.status_code == 200, resp.text
    assert resp.json()["is_default"] is True
    assert resp.json()["name"] is None
    assert (await test_app.get("/api/v1/profile")).json()["is_default"] is True


async def test__api__profile__does_not_leak_into_settings(test_app: AsyncClient) -> None:
    await test_app.put("/api/v1/profile", json=_PROFILE)

    settings = (await test_app.get("/api/v1/settings")).json()
    exported = (await test_app.post("/api/v1/data/export", json={})).json()["settings"]

    for body in (settings, exported):
        assert "profile_name" not in body
        assert "profile_email" not in body


async def test__api__put_settings__cannot_write_profile_keys(test_app: AsyncClient) -> None:
    resp = await test_app.put("/api/v1/settings", json={"profile_name": "Чужой", "profile_email": "x@example.org"})

    assert resp.status_code == 200, resp.text
    assert (await test_app.get("/api/v1/profile")).json()["is_default"] is True


async def test__api__import_data__profile_keys_ignored(test_app: AsyncClient) -> None:
    await test_app.put("/api/v1/profile", json=_PROFILE)

    resp = await test_app.post(
        "/api/v1/data/import",
        json={
            "version": "1.0",
            "exported_at": "2026-01-01T00:00:00Z",
            "encrypted": False,
            "settings": {"theme": "light", "profile_name": "Чужой", "profile_email": "x@example.org"},
        },
    )

    assert resp.status_code == 201, resp.text
    profile = (await test_app.get("/api/v1/profile")).json()
    assert profile["name"] == "Алиса Иванова"


def _head_identity(project: dict[str, Any]) -> str:
    git_dir = Path(project["folder"]) / ".hse-studio" / "git"
    out = subprocess.run(  # noqa: S603
        ["git", "--git-dir", str(git_dir), "log", "-1", "--format=%an,%ae,%cn,%ce"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


async def test__api__snapshot_after_put_profile__is_signed_with_profile(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await create_project(test_app, tmp_path / "proj")
    assert _head_identity(project).startswith("HSE Studio,bot@hse-studio.local")
    await test_app.put("/api/v1/profile", json=_PROFILE)
    edit_tracked_file(project, "signed by profile")

    resp = await test_app.post(f"/api/v1/projects/{project['id']}/vcs/snapshots", json={"message": "mine"})

    assert resp.status_code == 200, resp.text
    assert _head_identity(project) == "Алиса Иванова,Alice@example.org,Алиса Иванова,Alice@example.org"


async def test__api__snapshot_after_delete_profile__is_signed_by_bot_again(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await create_project(test_app, tmp_path / "proj")
    await test_app.put("/api/v1/profile", json=_PROFILE)
    await test_app.delete("/api/v1/profile")
    edit_tracked_file(project, "bot again")

    await test_app.post(f"/api/v1/projects/{project['id']}/vcs/snapshots", json={"message": "mine"})

    assert _head_identity(project).startswith("HSE Studio,bot@hse-studio.local")


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, 0), (60, 60), (30, 60), (900, 900)],
)
async def test__api__git_fetch_interval__is_stored_with_minimum_and_zero_means_off(
    test_app: AsyncClient, value: int, expected: int
) -> None:
    assert (await test_app.get("/api/v1/settings")).json()["git_fetch_interval_s"] == 300

    resp = await test_app.put("/api/v1/settings", json={"git_fetch_interval_s": value})

    assert resp.status_code == 200, resp.text
    assert resp.json()["git_fetch_interval_s"] == expected


async def test__api__git_fetch_interval__negative__rejected(test_app: AsyncClient) -> None:
    resp = await test_app.put("/api/v1/settings", json={"git_fetch_interval_s": -1})

    assert resp.status_code == 400
