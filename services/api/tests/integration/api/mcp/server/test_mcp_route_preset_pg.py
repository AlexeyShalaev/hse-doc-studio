"""MCP облака: маршрут из шаблона (docs/design/signing-route.md, 15.12; docs/design/mcp.md, M25).

Записи нет: «Вернуть как в шаблоне» и «Вернуть место из шаблона» только в интерфейсе. `send_for_signing` создаёт
черновик тем же сценарием, что кнопка, поэтому пресет применяется сам: места из шаблона включены, и отправка проходит
без ручной расстановки. Чтение отдаёт пресет и его отличия всегда, а не только тому, кто управляет маршрутом.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.integration.api.mcp.server.test_mcp_server_pg import _call, _enable, _token
from tests.integration.api.signing_routes.preset_stand import PRESET_VERSION
from tests.integration.api.signing_routes.stand import TOPIC, TOPIC_DOCS, Person, Project, Stand, make_project, person

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

PROPOSAL, APPLICATION = TOPIC_DOCS
_SEND = "send_for_signing"


def _body(result: dict[str, Any]) -> Any:
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


async def _project(stand: Stand, supervisor_role: str = "university") -> tuple[Project, Person, Person]:
    author = await person(stand, "Иванов Иван Иванович")
    supervisor = await person(stand, "Петров Пётр Петрович")
    project = make_project(
        stand, author, version=PRESET_VERSION, supervisor={"name": "Петров Пётр Петрович", "role": supervisor_role}
    )
    await project.member(supervisor, "reviewer", "supervisor")
    return project, author, supervisor


async def test__send_for_signing__applies_the_preset__places_from_the_template_no_manual_placing(
    preset_packs: Path, stand: Stand
) -> None:
    _enable(stand, enabled_dangerous=[_SEND])
    project, author, _ = await _project(stand)
    for doc_id in TOPIC_DOCS:
        project.build(doc_id)
    project.png(author, "author")

    sent = _body(
        _call(stand, _token(stand, author.email, ["mcp"]), _SEND, {"project_id": project.id, "profile_id": TOPIC})
    )

    assert sent["route"]["status"] == "active"
    assert [[p["persona"] for p in step] for step in sent["route"]["steps"]] == [["author"], ["supervisor"]]
    plan = _body(
        _call(
            stand,
            _token(stand, author.email, ["mcp"]),
            "get_signature_plan",
            {"project_id": project.id, "profile_id": TOPIC},
        )
    )
    places = {(doc["doc_id"], slot["slot_id"]): slot["place"] for doc in plan["docs"] for slot in doc["slots"]}
    assert places == {
        (PROPOSAL, "supervisor"): "pack",
        (APPLICATION, "author"): "pack",
        (APPLICATION, "supervisor"): "pack",
    }


async def test__get_signing_route__preset_differs_and_hint__reviewer_sees_it_too(
    preset_packs: Path, stand: Stand
) -> None:
    _enable(stand)
    project, author, supervisor = await _project(stand)
    route = project.call(author, "POST", project.routes, json={"profile_id": TOPIC}).json()
    steps = [
        [{"id": p["id"], "persona": p["persona"], "user_id": p["user_id"], "invitation_id": p["invitation_id"]}]
        for step in route["steps"]
        for p in step
    ]
    changed = project.call(
        author,
        "PUT",
        f"{project.routes}/{route['id']}",
        json={
            "steps": steps,
            "extra_slots": [{"doc_id": APPLICATION, "slot_id": "academic_supervisor"}],
            "deadline": None,
            "message": None,
        },
    )
    assert changed.status_code == 200, changed.text

    args = {"project_id": project.id, "profile_id": TOPIC}
    shown = _body(_call(stand, _token(stand, supervisor.email, ["mcp"]), "get_signing_route", args))["route"]

    assert shown["preset"]["version"] == PRESET_VERSION
    assert shown["preset"]["differs"] == ["order", "slots"]
    assert "Вернуть как в шаблоне может автор в интерфейсе" in shown["preset_hint"]
    slots = {(doc["doc_id"], slot["slot_id"]): slot["added_by"] for doc in shown["docs"] for slot in doc["slots"]}
    assert slots[(APPLICATION, "academic_supervisor")] == "author"
    assert slots[(APPLICATION, "author")] is None


async def test__list_submission_profiles__route_preset_with_conditions_met_in_the_project(
    preset_packs: Path, stand: Stand
) -> None:
    _enable(stand)
    project, author, _ = await _project(stand, supervisor_role="company")

    profiles = _body(
        _call(stand, _token(stand, author.email, ["mcp"]), "list_submission_profiles", {"project_id": project.id})
    )

    by_id = {p["id"]: p for p in profiles}
    preset = by_id[TOPIC]["route_preset"]
    assert preset["steps"] == [["author"], ["supervisor"], ["academic_supervisor"]]
    assert {(s["slot_id"], s["met"]) for s in preset["signing_slots"]} == {
        ("academic_supervisor", True),
        ("co_supervisor", False),
    }
    # Места по документам у версии есть: у точки без signing_slots пресет из порядка и мест, у точки без подписей нет.
    assert by_id["final"]["route_preset"] == {"version": PRESET_VERSION, "steps": [["author"]], "signing_slots": []}
    assert by_id["pre-defence"]["route_preset"] is None
