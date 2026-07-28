from __future__ import annotations

from pathlib import Path

from hse_doc_studio.api.config import settings
from httpx import AsyncClient

from tests.fixtures.app import UnsupportedSelfUpdateGateway
from tests.integration.api.system.conftest import updatable_client


async def test__api__system_info__returns_shape(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/system/info")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    for key in (
        "version",
        "deployment_mode",
        "os",
        "os_version",
        "python_version",
        "image_ref",
        "source_url",
        "github_repo",
        "license",
        "docker",
        "can_self_update",
        "built",
        "latest_version",
        "update_available",
        "update_checked_at",
        "update_feed_enabled",
        "latest_release_date",
        "latest_release_notes",
    ):
        assert key in data, f"missing key: {key}"

    # version is the backend's real version, not a hardcoded UI literal
    assert data["version"] == settings.get_app_version()
    assert data["deployment_mode"] in ("all-in-one", "standard", "native")
    assert data["docker"] in ("running", "stopped")
    assert isinstance(data["can_self_update"], bool)
    assert data["github_repo"]
    assert data["source_url"].startswith("http")
    # Проверок ещё не было: состояние обновлений отвечает по кэшу, а кэш пуст —
    # и главное, эта ручка НЕ ходит в сеть за ответом (см. test_updates.py).
    assert data["latest_version"] == settings.get_app_version()
    assert data["update_available"] is False
    assert data["update_checked_at"] is None


async def test__api__self_update__409_when_deployment_cannot_replace_itself(test_app: AsyncClient) -> None:
    # Tests don't run the all-in-one image, so the gate must reject self-update.
    resp = await test_app.post("/api/v1/system/self-update", json={"version": "0.2.0"})

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "not_self_updatable"


async def test__api__self_update__400_on_invalid_version(updatable_app: AsyncClient) -> None:
    # Версия попадает в имя образа и в аргументы docker — инъекцию режем до вызова.
    resp = await updatable_app.post(
        "/api/v1/system/self-update",
        json={"version": "0.2.0; rm -rf /"},
    )

    assert resp.status_code == 400, resp.text


async def test__api__self_update__202_starts_the_updater(
    updatable_app: AsyncClient,
    self_updater: UnsupportedSelfUpdateGateway,
) -> None:
    resp = await updatable_app.post("/api/v1/system/self-update", json={"version": "0.2.0"})

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["started"] is True
    assert body["target_image"] == self_updater.target_image("0.2.0")
    assert self_updater.started_versions == ["0.2.0"]


async def test__api__self_update__older_version__is_allowed_as_a_rollback(
    updatable_app: AsyncClient,
    self_updater: UnsupportedSelfUpdateGateway,
) -> None:
    # Переключение назад — такое же законное действие, как обновление вперёд:
    # свежая версия может не подойти, и вернуться нужно без консоли.
    resp = await updatable_app.post("/api/v1/system/self-update", json={"version": "0.0.1"})

    assert resp.status_code == 202, resp.text
    assert self_updater.started_versions == ["0.0.1"]


async def test__api__self_update__busy_system__still_switches_on_explicit_request(
    tmp_path: Path,
) -> None:
    # Занятость останавливает только ФОНОВОЕ обновление: нажавший кнопку видит,
    # что прерывает, и запрещать ему — значит запереть его на сломанной версии.
    updater = UnsupportedSelfUpdateGateway(can_update=True, busy=True)
    async for client in updatable_client(tmp_path, updater):
        resp = await client.post("/api/v1/system/self-update", json={"version": "0.2.0"})

        assert resp.status_code == 202, resp.text
        assert updater.started_versions == ["0.2.0"]


async def test__api__self_update__updater_fails_to_start__returns_409(tmp_path: Path) -> None:
    updater = UnsupportedSelfUpdateGateway(can_update=True, starts=False)
    async for client in updatable_client(tmp_path, updater):
        resp = await client.post("/api/v1/system/self-update", json={"version": "0.2.0"})

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["code"] == "self_update_failed"
