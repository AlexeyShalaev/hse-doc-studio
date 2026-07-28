from __future__ import annotations

from typing import Any

import pytest
from hse_doc_studio.api.config import OfficeConvertConfig, OfficeEditorConfig
from hse_doc_studio.api.config import settings as app_settings
from httpx import AsyncClient
from pytest_mock import MockerFixture

_SERVICES = ("convert", "editor")


def _service_config(service: str) -> OfficeConvertConfig | OfficeEditorConfig:
    return app_settings.office_convert if service == "convert" else app_settings.office_editor


async def test__get_status__called__returns_full_shape(test_app: AsyncClient) -> None:
    # Real GetOfficeServicesStatusUC call — docker_status() never raises, and
    # the per-container inspect_state() calls are only made when Docker is
    # actually available, so this works regardless of the test host's Docker
    # state.
    resp = await test_app.get("/api/v1/office-services/status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    services = data["services"]
    assert {s["service"] for s in services} == set(_SERVICES)
    for s in services:
        assert isinstance(s["active_image"], str)
        assert s["active_image"]
        assert s["label_hint"] in ("gotenberg", "onlyoffice")
        assert isinstance(s["image_installed"], bool)
        container = s["container"]
        assert isinstance(container["present"], bool)
        assert isinstance(container["running"], bool)
        assert container["status_text"] is None or isinstance(container["status_text"], str)


@pytest.mark.parametrize("service", _SERVICES)
async def test__list_images__known_service__returns_full_shape(test_app: AsyncClient, service: str) -> None:
    # Fresh tmp_path data_dir has no override in settings.json, so active_image
    # resolves to the deployment default for that service.
    resp = await test_app.get(f"/api/v1/office-services/{service}/images")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    cfg = _service_config(service)
    assert data["active_image"] == cfg.image
    assert data["allowed_repos"] == cfg.allowed_repos
    assert isinstance(data["images"], list)


async def test__list_images__unknown_service__returns_422(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/office-services/unknown/images")

    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("service", _SERVICES)
async def test__list_remote_tags__disallowed_repo__returns_400(test_app: AsyncClient, service: str) -> None:
    resp = await test_app.get(f"/api/v1/office-services/{service}/images/remote", params={"repo": "evil/image"})

    assert resp.status_code == 400, resp.text


@pytest.mark.parametrize("service", _SERVICES)
async def test__list_remote_tags__allowed_repo__returns_mapped_tags(
    test_app: AsyncClient, mocker: MockerFixture, service: str
) -> None:
    # `_http_get_json` hits Docker Hub over `urllib` (not `httpx`), so
    # `httpx_mock` can't intercept it — patch the function directly instead.
    cfg = _service_config(service)
    repo = cfg.allowed_repos[0]
    canned: dict[str, Any] = {
        "results": [
            {"name": "latest", "full_size": 654321, "last_updated": "2026-02-02T00:00:00Z"},
        ]
    }
    mocker.patch(
        "hse_doc_studio.infra.compile.docker_image_manager._http_get_json",
        return_value=canned,
    )

    resp = await test_app.get(f"/api/v1/office-services/{service}/images/remote", params={"repo": repo})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["repo"] == repo
    assert data["tags"] == [{"name": "latest", "size_bytes": 654321, "last_updated": "2026-02-02T00:00:00Z"}]


async def test__list_remote_tags__no_repo_param__defaults_to_first_allowed_repo(
    test_app: AsyncClient, mocker: MockerFixture
) -> None:
    mocker.patch(
        "hse_doc_studio.infra.compile.docker_image_manager._http_get_json",
        return_value={"results": []},
    )

    resp = await test_app.get("/api/v1/office-services/convert/images/remote")

    assert resp.status_code == 200, resp.text
    assert resp.json()["repo"] == app_settings.office_convert.allowed_repos[0]


@pytest.mark.parametrize("service", _SERVICES)
async def test__set_active_image__disallowed_repo__returns_400(test_app: AsyncClient, service: str) -> None:
    resp = await test_app.post(f"/api/v1/office-services/{service}/images/active", json={"image": "evil/image:latest"})

    assert resp.status_code == 400, resp.text


async def test__set_active_image__unknown_service__returns_422(test_app: AsyncClient) -> None:
    resp = await test_app.post("/api/v1/office-services/unknown/images/active", json={"image": "x/y:z"})

    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("service", _SERVICES)
async def test__install_image__disallowed_repo__returns_400(test_app: AsyncClient, service: str) -> None:
    # Allowlist check happens before `docker pull` is ever invoked, so this
    # never opens a real SSE stream or subprocess.
    resp = await test_app.get(
        f"/api/v1/office-services/{service}/images/install", params={"image": "evil/image:latest"}
    )

    assert resp.status_code == 400, resp.text


async def test__install_image__unknown_service__returns_422(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/office-services/unknown/images/install", params={"image": "x/y:z"})

    assert resp.status_code == 422, resp.text
