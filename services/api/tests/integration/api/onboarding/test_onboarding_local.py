"""Онбординг локальной Студии: состояние в data_dir, без входа и без базы."""

from __future__ import annotations

from httpx import AsyncClient


async def test__api__get__fresh_install__pending(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/onboarding")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"
    assert resp.json()["answers"] == {}


async def test__api__patch_then_get__state_persists(test_app: AsyncClient) -> None:
    resp = await test_app.patch(
        "/api/v1/onboarding",
        json={"status": "in_progress", "step": "demo.build", "scenario_version": 1, "answers": {"role": "student"}},
    )

    assert resp.status_code == 200, resp.text
    body = (await test_app.get("/api/v1/onboarding")).json()
    assert (body["status"], body["step"], body["scenario_version"]) == ("in_progress", "demo.build", 1)
    assert body["answers"] == {"role": "student"}
    assert body["started_at"] is not None


async def test__api__patch__unknown_question__422(test_app: AsyncClient) -> None:
    resp = await test_app.patch("/api/v1/onboarding", json={"answers": {"age": "20"}})

    assert resp.status_code == 422


async def test__api__patch__suggested_from_client__422(test_app: AsyncClient) -> None:
    resp = await test_app.patch("/api/v1/onboarding", json={"status": "suggested"})

    assert resp.status_code == 422


async def test__api__reset__after_skip__pending_again(test_app: AsyncClient) -> None:
    await test_app.patch("/api/v1/onboarding", json={"status": "skipped", "step": ""})

    resp = await test_app.post("/api/v1/onboarding/reset")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"
