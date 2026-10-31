"""«Мои раннеры»: личные токены, регистрация, свой список, изоляция, пауза, переименование, смена токена, отзыв."""

from __future__ import annotations

import pytest

from tests.integration.api.personal.conftest import Stand

pytestmark = pytest.mark.pg


async def test__personal_token__registers_a_personal_runner_seen_only_by_its_owner(stand: Stand) -> None:
    anna, boris = await stand.person("anna"), await stand.person("boris")
    created = stand.client.post(
        "/api/v1/account/runner-tokens", json={"label": "Дом", "ttl_hours": 24}, headers=anna.headers
    )
    assert created.status_code == 201
    body = created.json()
    assert body["secret"].startswith("hsrt_")
    assert f"HSE_RUNNER__TOKEN={body['secret']}" in body["command"]
    assert "docker run" in body["docker_command"]
    assert body["secret"] not in stand.client.get("/api/v1/account/runner-tokens", headers=anna.headers).text

    runner = stand.register(body["secret"], "MacBook")
    runner_id = runner["X-Runner-Id"]

    mine = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert [(r["id"], r["name"], r["state"], r["host_kind"]) for r in mine] == [(runner_id, "MacBook", "online", "cli")]
    tokens = stand.client.get("/api/v1/account/runner-tokens", headers=anna.headers).json()
    assert [t["used"] for t in tokens] == [True]
    assert stand.client.get("/api/v1/account/runners", headers=boris.headers).json() == []
    for method, path in (
        ("PATCH", f"/api/v1/account/runners/{runner_id}"),
        ("POST", f"/api/v1/account/runners/{runner_id}/rotate-token"),
        ("DELETE", f"/api/v1/account/runners/{runner_id}"),
        ("DELETE", f"/api/v1/account/runner-tokens/{tokens[0]['id']}"),
    ):
        response = stand.client.request(method, path, json={"name": "x", "paused": None}, headers=boris.headers)
        assert response.status_code == 404, (method, path)
    admin_view = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert admin_view[0]["revoked"] is False


async def test__my_runner__rename_pause_rotate_and_revoke(stand: Stand) -> None:
    anna = await stand.person("anna")
    runner = stand.personal_runner(anna)
    runner_id = runner.pop("X-Runner-Id")
    path = f"/api/v1/account/runners/{runner_id}"

    renamed = stand.client.patch(path, json={"name": "  Рабочий   ПК ", "paused": None}, headers=anna.headers)
    assert renamed.json()["name"] == "Рабочий ПК"
    # Имя из интерфейса раннер своим /announce не перетирает.
    announce = stand.client.post(
        "/api/runner/v1/announce",
        json={
            "name": "hostname",
            "version": "0.3.1",
            "tags": ["tex"],
            "concurrency": 2,
            "ai_concurrency": 2,
            "host_kind": "desktop",
            "features": ["announce", "offline", "ai_slots", "ai_relay", "future_thing"],
            "ai_endpoints": [{"name": "ollama", "flavor": "ollama"}],
        },
        headers=runner,
    )
    assert announce.status_code == 200, announce.text
    assert announce.json() == {
        "runner_id": runner_id,
        "server_features": ["ai_relay", "ai_slots", "announce", "offline"],
        "owner_kind": "user",
        "paused": False,
        "relay_keepalive_s": 2,
    }
    (view,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert (view["name"], view["host_kind"], view["ai_endpoints"], view["version"]) == (
        "Рабочий ПК",
        "desktop",
        [{"name": "ollama", "flavor": "ollama"}],
        "0.3.1",
    )
    assert view["last_seen_ip"] is not None

    paused = stand.client.patch(path, json={"name": None, "paused": True}, headers=anna.headers).json()
    assert (paused["paused"], paused["state"]) == (True, "paused")

    rotated = stand.client.post(f"{path}/rotate-token", headers=anna.headers)
    assert rotated.status_code == 200
    assert "HSE_RUNNER__RUNNER_TOKEN=hsrn_" in rotated.json()["command"]
    old = stand.client.post("/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 1}, headers=runner)
    assert old.status_code == 401
    fresh = {"Authorization": f"Bearer {rotated.json()['runner_token']}"}
    assert (
        stand.client.post("/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 1}, headers=fresh).status_code == 200
    )

    assert stand.client.delete(path, headers=anna.headers).status_code == 204
    (gone,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert (gone["revoked"], gone["state"]) == (True, "revoked")
    assert stand.client.post(f"{path}/rotate-token", headers=anna.headers).json()["code"] == "runner_revoked"
    assert (
        stand.client.post("/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 1}, headers=fresh).status_code == 401
    )


async def test__personal_tokens__limit_of_five_unused(stand: Stand) -> None:
    anna = await stand.person("anna")
    for _ in range(5):
        assert stand.client.post("/api/v1/account/runner-tokens", json={}, headers=anna.headers).status_code == 201
    over = stand.client.post("/api/v1/account/runner-tokens", json={}, headers=anna.headers)
    assert (over.status_code, over.json()["code"]) == (409, "personal_runner_limit")


async def test__runner_limit_and_disabled_installation(stand: Stand) -> None:
    anna = await stand.person("anna")
    admin = stand.admin()
    admin.put("/api/admin/settings/build", json={"personal_runners_max_per_user": 1}).raise_for_status()
    stand.personal_runner(anna, "first")
    secret = stand.client.post("/api/v1/account/runner-tokens", json={}, headers=anna.headers).json()["secret"]
    over = stand.client.post(
        "/api/runner/v1/register",
        json={
            "name": "second",
            "protocol": 1,
            "version": "0.3.0",
            "tags": [],
            "concurrency": 1,
            "resource_class": "standard",
        },
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert (over.status_code, over.json()["code"]) == (409, "runner_limit")

    admin.put("/api/admin/settings/build", json={"personal_runners_enabled": False}).raise_for_status()
    refused = stand.client.post("/api/v1/account/runner-tokens", json={}, headers=anna.headers)
    assert (refused.status_code, refused.json()["code"]) == (403, "personal_runners_disabled")
    (runner,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert runner["state"] == "disabled"


async def test__runner_offline_and_deregister(stand: Stand) -> None:
    anna = await stand.person("anna")
    runner = stand.personal_runner(anna)
    runner_id = runner.pop("X-Runner-Id")
    assert stand.client.post("/api/runner/v1/offline", headers=runner).status_code == 204
    (view,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert view["state"] == "offline"
    assert stand.client.post("/api/runner/v1/deregister", headers=runner).status_code == 204
    (view,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert (view["id"], view["revoked"]) == (runner_id, True)


async def test__admin__pauses_and_revokes_personal_runner_but_cannot_rotate_its_token(stand: Stand) -> None:
    anna = await stand.person("anna")
    runner_id = stand.personal_runner(anna)["X-Runner-Id"]
    admin = stand.admin()

    rotated = admin.post(f"/api/admin/runners/{runner_id}/rotate-token")
    assert (rotated.status_code, rotated.json()["code"]) == (403, "forbidden")
    assert admin.patch(f"/api/admin/runners/{runner_id}", json={"paused": True}).status_code == 204
    (view,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert (view["state"], view["paused_by"]) == ("paused", "admin")
    # Пауза админа это модерация: хозяин её не снимает, админ снимает.
    resumed = stand.client.patch(f"/api/v1/account/runners/{runner_id}", json={"paused": False}, headers=anna.headers)
    assert (resumed.status_code, resumed.json()["code"]) == (403, "runner_paused_by_admin")
    assert admin.patch(f"/api/admin/runners/{runner_id}", json={"paused": False}).status_code == 204
    (view,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert view["paused_by"] is None
    assert admin.delete(f"/api/admin/runners/{runner_id}").status_code == 204
    (view,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert view["revoked"] is True


async def test__disabled_owner__runner_is_refused_and_deletion_revokes_it(stand: Stand) -> None:
    anna = await stand.person("anna")
    runner = stand.personal_runner(anna)
    runner_id = runner.pop("X-Runner-Id")
    admin = stand.admin()

    assert admin.post(f"/api/admin/users/{anna.id}/disable").status_code == 200
    refused = stand.client.post("/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 1}, headers=runner)
    assert (refused.status_code, refused.json()["code"]) == (403, "runner_disabled")

    assert admin.delete(f"/api/admin/users/{anna.id}").status_code == 204
    gone = stand.client.post("/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 1}, headers=runner)
    assert gone.status_code == 401
    listed = admin.get("/api/admin/runners").json()["items"]
    assert [r["revoked"] for r in listed if r["id"] == runner_id] == [True]


async def test__admin__lists_personal_runners_with_owner_and_filters_by_kind(stand: Stand) -> None:
    anna = await stand.person("anna")
    runner_id = stand.personal_runner(anna, "MacBook Анны")["X-Runner-Id"]
    admin = stand.admin()

    personal = admin.get("/api/admin/runners", params={"owner_kind": "user"}).json()["items"]
    assert [(r["id"], r["owner_kind"], r["owner"]["id"], r["owner"]["email"]) for r in personal] == [
        (runner_id, "user", anna.id, anna.email)
    ]
    assert admin.get("/api/admin/runners", params={"owner_kind": "instance"}).json()["items"] == []

    admin.put("/api/admin/settings/build", json={"personal_runners_enabled": False}).raise_for_status()
    (row,) = admin.get("/api/admin/runners").json()["items"]
    assert row["status"] == "disabled"
    settings = admin.get("/api/admin/settings/build").json()
    assert (settings["personal_runners_enabled"], settings["fields"]["runners.personal_enabled"]["source"]) == (
        False,
        "admin",
    )


async def test__bootstrap__personal_runners_capability_follows_the_setting(stand: Stand) -> None:
    # Bootstrap знает человека по сессии: берём сессию админа из окружения.
    admin = stand.admin()
    boot = admin.get("/api/v1/session/bootstrap").json()
    assert boot["capabilities"]["personal_runners"] is True
    assert boot["capabilities"]["remote_runner"] is False
    assert stand.client.get("/api/v1/session/bootstrap").json()["capabilities"]["personal_runners"] is False
    admin.put("/api/admin/settings/build", json={"personal_runners_enabled": False}).raise_for_status()
    off = admin.get("/api/v1/session/bootstrap").json()
    assert off["capabilities"]["personal_runners"] is False


async def test__personal_runners_turned_off__refused_runner_is_offline_after_turning_back_on(stand: Stand) -> None:
    """Раннер, получивший runner_disabled, завершается: после включения он «не в сети», а не «в сети» ещё минуту."""
    anna = await stand.person("anna")
    runner = stand.personal_runner(anna)
    runner.pop("X-Runner-Id")
    admin = stand.admin()

    admin.put("/api/admin/settings/build", json={"personal_runners_enabled": False}).raise_for_status()
    refused = stand.client.post("/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 1}, headers=runner)
    assert (refused.status_code, refused.json()["code"]) == (403, "runner_disabled")
    admin.put("/api/admin/settings/build", json={"personal_runners_enabled": True}).raise_for_status()

    (view,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert view["state"] == "offline"
    # Вернувшийся раннер снова в сети с первого опроса.
    assert stand.client.post(
        "/api/runner/v1/poll", json={"wait_s": 0, "free_slots": 1}, headers=runner
    ).status_code in (
        200,
        204,
    )
    (view,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert view["state"] == "online"
