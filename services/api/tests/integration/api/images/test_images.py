from __future__ import annotations

from typing import Any

from hse_doc_studio.api.config import settings as app_settings
from httpx import AsyncClient
from pytest_mock import MockerFixture


async def test__docker_status__called__returns_full_shape(test_app: AsyncClient) -> None:
    # Real DockerImageManager.docker_status() call — it never raises (catches
    # OSError internally), so this works whether or not Docker is actually
    # installed/running on the machine running the tests.
    resp = await test_app.get("/api/v1/compile/docker-status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    for key in ("available", "version", "detail"):
        assert key in data, f"missing key: {key}"
    assert isinstance(data["available"], bool)
    if data["available"]:
        assert isinstance(data["version"], str)


async def test__list_images__called__returns_full_shape(test_app: AsyncClient) -> None:
    # Fresh tmp_path data_dir has no `compile_image` override in settings.json,
    # so active_image resolves to the deployment default.
    resp = await test_app.get("/api/v1/compile/images")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data["active_image"], str)
    assert data["active_image"]
    assert data["allowed_repos"] == app_settings.compile.allowed_repos
    assert isinstance(data["installed"], list)


async def test__list_remote_tags__disallowed_repo__returns_400(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/compile/images/remote", params={"repo": "evil/image"})

    assert resp.status_code == 400, resp.text


async def test__list_remote_tags__allowed_repo__returns_mapped_tags(
    test_app: AsyncClient, mocker: MockerFixture
) -> None:
    # `_http_get_json` is a plain top-level function that hits Docker Hub over
    # `urllib` — patch it directly so the real network is never touched.
    repo = app_settings.compile.allowed_repos[0]
    canned: dict[str, Any] = {
        "results": [
            {"name": "latest", "full_size": 123456, "last_updated": "2026-01-01T00:00:00Z"},
            {"name": "no-size-or-date"},
        ]
    }
    mocker.patch(
        "hse_doc_studio.infra.compile.docker_image_manager._http_get_json",
        return_value=canned,
    )

    resp = await test_app.get("/api/v1/compile/images/remote", params={"repo": repo})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["repo"] == repo
    assert data["tags"] == [
        {"name": "latest", "size_bytes": 123456, "last_updated": "2026-01-01T00:00:00Z"},
        {"name": "no-size-or-date", "size_bytes": 0, "last_updated": None},
    ]


async def test__set_active_image__disallowed_repo__returns_400(test_app: AsyncClient) -> None:
    resp = await test_app.post("/api/v1/compile/images/active", json={"image": "evil/image:latest"})

    assert resp.status_code == 400, resp.text


async def test__remove_image__active_image__returns_400(test_app: AsyncClient) -> None:
    # SetActiveImageUC guards refusal to remove the active image before ever
    # invoking `docker image rm` — with no settings override, the active image
    # is the deployment default, so this never reaches a subprocess.
    resp = await test_app.delete("/api/v1/compile/images", params={"image": app_settings.compile.image})

    assert resp.status_code == 400, resp.text


async def test__install_image__disallowed_repo__returns_400(test_app: AsyncClient) -> None:
    # Allowlist check happens before `docker pull` is ever invoked, so this
    # never opens a real SSE stream or subprocess.
    resp = await test_app.get("/api/v1/compile/images/install", params={"image": "evil/image:latest"})

    assert resp.status_code == 400, resp.text
