"""Онбординг на сервере: у каждого пользователя своя строка, чужое состояние не видно."""

from __future__ import annotations

import pytest

from tests.integration.api.personal.conftest import Stand, stand

__all__ = ["stand"]

pytestmark = pytest.mark.pg


async def test__new_user__pending_and_isolated_from_other_user(stand: Stand) -> None:
    anna, boris = await stand.person("anna"), await stand.person("boris")

    done = stand.client.patch(
        "/api/v1/onboarding", json={"status": "completed", "answers": {"role": "supervisor"}}, headers=anna.headers
    )

    assert done.status_code == 200, done.text
    assert done.json()["finished_at"] is not None
    assert stand.client.get("/api/v1/onboarding", headers=anna.headers).json()["status"] == "completed"
    other = stand.client.get("/api/v1/onboarding", headers=boris.headers).json()
    assert (other["status"], other["answers"]) == ("pending", {})


async def test__reset__returns_tour_to_start_and_keeps_answers(stand: Stand) -> None:
    anna = await stand.person("anna")
    stand.client.patch(
        "/api/v1/onboarding",
        json={"status": "skipped", "step": "demo.git", "answers": {"role": "student", "git": "none"}},
        headers=anna.headers,
    )

    reset = stand.client.post("/api/v1/onboarding/reset", headers=anna.headers)

    assert reset.status_code == 200, reset.text
    body = reset.json()
    assert (body["status"], body["step"]) == ("pending", None)
    assert body["answers"] == {"role": "student", "git": "none"}


async def test__anonymous__cannot_read_onboarding(stand: Stand) -> None:
    assert stand.client.get("/api/v1/onboarding").status_code in {401, 403}
