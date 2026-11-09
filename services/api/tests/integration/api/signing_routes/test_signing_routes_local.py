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
        ("GET", f"{one}/task", None),
        ("GET", f"{one}/task/image", None),
        ("POST", f"{one}/task/approve", {"expected": {}, "method": None, "sign": None}),
        ("POST", f"{one}/task/sign", {"expected": {}, "identity_id": None, "passphrase": None}),
        ("POST", f"{one}/task/return", {"comment": "Уточните цель проекта"}),
        ("PUT", f"{one}/task/plate", {"identity_id": ROUTE}),
    ]

    for method, path, body in calls:
        resp = await test_app.request(method, path, json=body)
        assert resp.status_code == 404, (method, path, resp.text)


async def test__local_studio__signing_task_uploads__not_found(test_app: AsyncClient) -> None:
    task = f"/api/v1/projects/{PROJECT}/signing-routes/{ROUTE}/task"

    image = await test_app.post(f"{task}/image", files={"file": ("s.png", b"png", "image/png")})
    plate = await test_app.post(f"{task}/plate/file", files={"file": ("c.pem", b"pem", "application/x-pem-file")})

    assert (image.status_code, plate.status_code) == (404, 404)
