"""Пакет точки, пока маршрут подписания не завершён (docs/design/signing-route.md, 12.8.1).

Пакет требует готовых обязательных подписей. Если они не готовы потому, что маршрут ещё идёт или его вернули,
отказ называет маршрут и того, кого ждём, а не «зафиксируйте новую версию».
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.api.signing_routes.signer_stand import NAMES, Trio, make_trio
from tests.integration.api.signing_routes.stand import TOPIC, Stand

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]


def _pack(trio: Trio) -> dict[str, Any]:
    body = {"profile_id": TOPIC, "items": [], "extra_items": [], "archive_format": "zip"}
    resp = trio.call(trio.author, "POST", f"{trio.project.base}/submissions", json=body)
    assert resp.status_code == 400, resp.text
    return dict(resp.json())


async def test__pack__route_in_progress__refused_with_the_route_and_who_it_waits_for(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor", "academic_supervisor"))
    trio.sent()

    body = _pack(trio)

    assert body["code"] == "pack_route_in_progress"
    assert (body["who"], body["step"], body["total"]) == (NAMES["supervisor"], 2, 3)
    assert body["detail"].startswith("Маршрут подписания не завершён (шаг 2 из 3, ждём: Петров Пётр Петрович)")


async def test__pack__route_returned__refused_with_send_again(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor", "academic_supervisor"))
    trio.sent()
    returned = trio.give_back(trio.supervisor)
    assert returned.status_code == 200, returned.text

    body = _pack(trio)

    assert body["code"] == "pack_route_returned"
