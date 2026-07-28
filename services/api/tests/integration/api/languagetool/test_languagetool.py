from __future__ import annotations

from httpx import AsyncClient


async def test__api__languagetool_status__returns_full_shape(test_app: AsyncClient) -> None:
    # Exercises the whole DI chain (router -> UC -> container manager + image
    # manager). Works whether or not Docker is present on the test host: when
    # the daemon is unreachable the status simply reports docker_available=False.
    resp = await test_app.get("/api/v1/languagetool/status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    for key in (
        "docker_available",
        "active_image",
        "image_installed",
        "container_present",
        "container_running",
        "healthy",
        "base_url",
    ):
        assert key in data, f"missing key: {key}"
    assert isinstance(data["docker_available"], bool)
    assert isinstance(data["active_image"], str)
    assert data["active_image"]


async def test__api__languagetool_remote_tags__rejects_unknown_repo(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/languagetool/images/remote", params={"repo": "evil/image"})
    assert resp.status_code == 400, resp.text
