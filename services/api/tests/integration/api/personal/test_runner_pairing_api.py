"""Сопряжение по коду устройства: устройство начинает, человек подтверждает, устройство получает токен один раз."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION

from tests.integration.api.personal.conftest import ORIGIN, Stand

pytestmark = pytest.mark.pg


def _start(stand: Stand) -> dict[str, object]:
    response = stand.client.post("/api/runner/v1/pair/start", json={"name": "MacBook Анны", "host_kind": "desktop"})
    assert response.status_code == 200, response.text
    return response.json()


def _poll(stand: Stand, device_code: str) -> dict[str, object]:
    # Интервал опроса 3 с; в тестах сервис узнаёт об опросах только по времени процесса, поэтому ждать нечего:
    # первый опрос каждой записи всегда разрешён, повторы проверяются отдельным тестом.
    response = stand.client.post("/api/runner/v1/pair/poll", json={"device_code": device_code})
    return {"status_code": response.status_code, **response.json()}


async def test__pairing__full_cycle_registers_a_desktop_runner(stand: Stand) -> None:
    anna = await stand.person("anna")
    started = _start(stand)
    code = str(started["user_code"])
    assert started["verification_uri_complete"] == f"{ORIGIN}/settings/runners/pair?code={code}"
    assert (started["expires_in"], started["interval"]) == (600, 3)

    info = stand.client.get(f"/api/v1/account/runner-pairings/{code.lower().replace('-', '')}", headers=anna.headers)
    assert info.status_code == 200
    assert (info.json()["name"], info.json()["host_kind"], info.json()["status"]) == (
        "MacBook Анны",
        "desktop",
        "pending",
    )

    approved = stand.client.post(
        f"/api/v1/account/runner-pairings/{code}", json={"decision": "approve"}, headers=anna.headers
    )
    assert approved.json()["status"] == "approved"
    again = stand.client.post(
        f"/api/v1/account/runner-pairings/{code}", json={"decision": "deny"}, headers=anna.headers
    )
    assert (again.status_code, again.json()["code"]) == (409, "runner_pairing_used")

    polled = _poll(stand, str(started["device_code"]))
    assert polled["status"] == "approved"
    token = str(polled["registration_token"])
    assert token.startswith("hsrt_")

    registered = stand.client.post(
        "/api/runner/v1/register",
        json={
            "name": "MacBook Анны",
            "protocol": RUNNER_PROTOCOL_VERSION,
            "version": "0.3.0",
            "tags": ["tex"],
            "concurrency": 1,
            "resource_class": "standard",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert registered.status_code == 200
    (runner,) = stand.client.get("/api/v1/account/runners", headers=anna.headers).json()
    assert runner["name"] == "MacBook Анны"
    # Токен сопряжения не виден в списке токенов, созданных вручную.
    assert stand.client.get("/api/v1/account/runner-tokens", headers=anna.headers).json() == []


async def test__pairing__deny_and_unknown_and_foreign(stand: Stand) -> None:
    anna, boris = await stand.person("anna"), await stand.person("boris")
    started = _start(stand)
    code = str(started["user_code"])
    denied = stand.client.post(
        f"/api/v1/account/runner-pairings/{code}", json={"decision": "deny"}, headers=anna.headers
    )
    assert denied.json()["status"] == "denied"
    assert _poll(stand, str(started["device_code"]))["status"] == "denied"
    # Решённое Анной сопряжение для Бориса не существует.
    foreign = stand.client.get(f"/api/v1/account/runner-pairings/{code}", headers=boris.headers)
    assert (foreign.status_code, foreign.json()["code"]) == (404, "runner_pairing_invalid")
    unknown = stand.client.get("/api/v1/account/runner-pairings/BCDF-2345", headers=anna.headers)
    assert unknown.status_code == 404
    assert _poll(stand, "hsdc_unknown")["status"] == "expired"


async def test__pairing__token_is_delivered_once_and_fast_polls_slow_down(stand: Stand) -> None:
    anna = await stand.person("anna")
    started = _start(stand)
    device = str(started["device_code"])
    assert _poll(stand, device)["status"] == "pending"
    fast = _poll(stand, device)
    assert (fast["status_code"], fast["code"]) == (429, "slow_down")
    stand.client.post(
        f"/api/v1/account/runner-pairings/{started['user_code']}", json={"decision": "approve"}, headers=anna.headers
    )
    # Первое устройство опрашивает слишком часто; у второго первый опрос после подтверждения сразу даёт токен.
    other = _start(stand)
    stand.client.post(
        f"/api/v1/account/runner-pairings/{other['user_code']}", json={"decision": "approve"}, headers=anna.headers
    )
    first = _poll(stand, str(other["device_code"]))
    assert first["status"] == "approved"
    assert first["registration_token"]
    # Повтор после выдачи: секрета больше нет (интервал выдержан не был, но выдача уже стёрла счётчик).
    second = _poll(stand, str(other["device_code"]))
    assert (second["status"], second["registration_token"]) == ("expired", None)


async def test__pairing__disabled_personal_runners(stand: Stand) -> None:
    stand.admin().put("/api/admin/settings/build", json={"personal_runners_enabled": False}).raise_for_status()
    refused = stand.client.post("/api/runner/v1/pair/start", json={"name": "x", "host_kind": "cli"})
    assert (refused.status_code, refused.json()["code"]) == (403, "runner_disabled")
