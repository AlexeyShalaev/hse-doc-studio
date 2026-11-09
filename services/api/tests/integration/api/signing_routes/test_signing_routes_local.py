"""Локальная Студия: маршрута подписания нет (docs/design/signing-route.md, раздел 6.9), ручки отвечают 404."""

from __future__ import annotations

from httpx import AsyncClient

PROJECT = "00000000-0000-4000-8000-000000000001"
ROUTE = "00000000-0000-4000-8000-000000000002"


async def test__local_studio__signing_routes__not_found(test_app: AsyncClient) -> None:
    base = f"/api/v1/projects/{PROJECT}/signing-routes"
    one = f"{base}/{ROUTE}"
    calls = [
        ("GET", base, None),
        ("POST", base, {"profile_id": "topic-approval"}),
        ("GET", one, None),
        ("PUT", one, {"steps": [], "extra_slots": [], "deadline": None, "message": None}),
        ("POST", f"{one}/preview", {}),
        ("POST", f"{one}/send", {"expected": {}, "sign": None}),
        ("POST", f"{one}/cancel", {}),
        ("POST", f"{one}/archive", {}),
    ]

    for method, path, body in calls:
        resp = await test_app.request(method, path, json=body)
        assert resp.status_code == 404, (method, path, resp.text)
