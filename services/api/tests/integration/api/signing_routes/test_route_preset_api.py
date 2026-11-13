"""Маршрут из шаблона на настоящем сервере (docs/design/signing-route.md, 15.5, 15.6, 15.11 и 15.12).

Пак `hse-cs-sse/coursework` 2026.1.4 с пресетом (`preset_stand`), точка «Заявка на тему КП». Черновик точки
применяет пресет и сразу пишет места; «Вернуть как в шаблоне» и «Вернуть место из шаблона»; ручные места, идущие
маршруты и проекты на версии без пресета не меняются.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.integration.api.signing_routes.preset_stand import PRESET_VERSION
from tests.integration.api.signing_routes.stand import (
    TOPIC,
    TOPIC_DOCS,
    Person,
    Project,
    Stand,
    make_project,
    person,
)

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

PROPOSAL, APPLICATION = TOPIC_DOCS
HSE = {"name": "Петров Пётр Петрович", "role": "university"}
COMPANY = {"name": "Петров Пётр Петрович", "role": "company"}
CONSULTANT = {"name": "Сидоров Сидор Сидорович", "role": "company"}


async def _project(stand: Stand, *, version: str = PRESET_VERSION, **people: Any) -> tuple[Project, Person, Person]:
    author = await person(stand, "Иванов Иван Иванович")
    supervisor = await person(stand, "Петров Пётр Петрович")
    project = make_project(stand, author, version=version, **({"supervisor": HSE} | people))
    await project.member(supervisor, "reviewer", "supervisor")
    return project, author, supervisor


def _create(project: Project, who: Person) -> Any:
    return project.call(who, "POST", project.routes, json={"profile_id": TOPIC})


def _signatures(project: Project) -> dict[str, Any]:
    path = project.folder / ".hse-studio" / "signatures.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _placements(project: Project) -> dict[str, dict[str, Any]]:
    return dict(_signatures(project).get("placements", {}))


def _steps(route: dict[str, Any]) -> list[list[str]]:
    return [[p["persona"] for p in step] for step in route["steps"]]


def _slots(route: dict[str, Any]) -> dict[tuple[str, str], tuple[bool, str | None, bool]]:
    return {
        (doc["doc_id"], slot["slot_id"]): (slot["extra"], slot["added_by"], slot["preset_optional"])
        for doc in route["docs"]
        for slot in doc["slots"]
    }


def _audit(stand: Stand, project: Project, action: str) -> list[dict[str, Any]]:
    resp = stand.admin().get("/api/admin/audit", params={"action": action, "target": project.id, "limit": 200})
    assert resp.status_code == 200, resp.text
    return list(resp.json()["items"])


def _restore(project: Project, who: Person, route_id: str) -> Any:
    return project.call(who, "POST", f"{project.routes}/{route_id}/restore-preset", json={})


def _restore_place(project: Project, who: Person, doc_id: str, slot_id: str, **body: Any) -> Any:
    return project.call(who, "POST", f"{project.base}/signatures/placements/{doc_id}/{slot_id}/restore", json=body)


def _put(project: Project, who: Person, route: dict[str, Any], **body: Any) -> Any:
    steps = [
        [{"id": p["id"], "persona": p["persona"], "user_id": p["user_id"], "invitation_id": p["invitation_id"]}]
        for step in route["steps"]
        for p in step
    ]
    payload = {"steps": steps, "extra_slots": [], "deadline": None, "message": None, **body}
    resp = project.call(who, "PUT", f"{project.routes}/{route['id']}", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- черновик ---------------------------------------------------------------------------------------------------------


async def test__create__supervisor_from_hse__author_and_supervisor_places_written_academic_not_added(
    preset_packs: Path, stand: Stand
) -> None:
    project, author, _ = await _project(stand)

    created = _create(project, author)
    placements = _placements(project)
    again = _create(project, author)

    assert created.status_code == 201, created.text
    route = created.json()
    assert _steps(route) == [["author"], ["supervisor"]]
    assert set(_slots(route)) == {(PROPOSAL, "supervisor"), (APPLICATION, "author"), (APPLICATION, "supervisor")}
    assert {value[1] for value in _slots(route).values()} == {None}
    preset = route["preset"]
    assert (preset["version"], preset["base_version"]) == (PRESET_VERSION, PRESET_VERSION)
    assert preset["steps"] == [["author"], ["supervisor"]]
    assert preset["extra_slots"] == []
    assert preset["skipped_by_condition"] == [
        {"doc_id": APPLICATION, "slot_id": "co_supervisor", "when": {"person": "co_supervisor", "role": None}},
        {"doc_id": APPLICATION, "slot_id": "academic_supervisor", "when": {"person": "supervisor", "role": "company"}},
    ]
    assert preset["differs"] == []
    # Три места включены там, где их ставит шаблон; у научрука на «Описании проекта» две метки даты.
    proposal = placements[PROPOSAL]["supervisor"]
    assert (proposal["enabled"], proposal["x_mm"], proposal["y_mm"]) == (True, 80, 139)
    assert [mark["format"] for mark in proposal["dates"]] == ["day", "month_word"]
    assert proposal["from_pack"]["version"] == PRESET_VERSION
    assert (placements[APPLICATION]["author"]["x_mm"], placements[APPLICATION]["author"]["enabled"]) == (165, True)
    assert placements[APPLICATION]["supervisor"]["y_mm"] == 168
    assert "academic_supervisor" not in placements[APPLICATION]
    # Повторный POST отдаёт тот же черновик и ничего не пишет.
    assert again.status_code == 200
    assert _placements(project) == placements
    [record] = _audit(stand, project, "signing_route.create")
    assert record["details"]["preset"] == {
        "version": PRESET_VERSION,
        "extra_slots": [],
        "optional": [],
        "placements": 3,
    }


async def test__create__supervisor_from_company__academic_on_step_3_missing_added_by_pack(
    preset_packs: Path, stand: Stand
) -> None:
    project, author, _ = await _project(stand, supervisor=COMPANY, co_supervisor=CONSULTANT)

    route = _create(project, author).json()

    assert _steps(route) == [["author"], ["supervisor", "co_supervisor"], ["academic_supervisor"]]
    assert _slots(route)[(APPLICATION, "academic_supervisor")] == (True, "pack", False)
    assert _slots(route)[(APPLICATION, "co_supervisor")] == (True, "pack", False)
    assert [p["membership"] for step in route["steps"] for p in step][-1] == "missing"
    assert route["preset"]["skipped_by_condition"] == []
    assert _placements(project)[APPLICATION]["academic_supervisor"]["y_mm"] == 238


async def test__create__manual_place_kept__ready_to_send_without_touching_places(
    preset_packs: Path, stand: Stand
) -> None:
    project, author, _ = await _project(stand)
    moved = project.call(
        author,
        "PATCH",
        f"{project.base}/signatures/placements/{APPLICATION}/author",
        json={"enabled": True, "x_mm": 120, "y_mm": 210},
    )
    assert moved.status_code == 200, moved.text
    for doc_id in TOPIC_DOCS:
        project.build(doc_id)
    project.png(author, "author")

    route = _create(project, author).json()
    preview = project.call(author, "POST", f"{project.routes}/{route['id']}/preview", json={}).json()

    author_place = _placements(project)[APPLICATION]["author"]
    assert (author_place["x_mm"], author_place["y_mm"], author_place["from_pack"]) == (120, 210, None)
    assert preview["blockers"] == []
    places = project.call(author, "GET", f"{project.base}/signatures").json()["placements"]
    assert places[APPLICATION]["author"]["origin"] == "manual"
    assert places[PROPOSAL]["supervisor"]["origin"] == "pack"


async def test__create__released_version_without_preset__nothing_written_no_preset(
    preset_packs: Path, stand: Stand
) -> None:
    project, author, _ = await _project(stand, version="2026.1.3")

    route = _create(project, author).json()

    assert route["preset"] is None
    assert _placements(project) == {}
    assert {value[1:] for value in _slots(route).values()} == {(None, False)}
    assert "preset" not in _audit(stand, project, "signing_route.create")[0]["details"]
    refused = _restore(project, author, route["id"])
    assert (refused.status_code, refused.json()["code"]) == (409, "no_preset")


# --- «Вернуть как в шаблоне» ------------------------------------------------------------------------------------------


async def test__restore_preset__author_changes__back_to_template_people_kept_audited_once(
    preset_packs: Path, stand: Stand
) -> None:
    project, author, supervisor = await _project(stand)
    route = _create(project, author).json()
    # Автор сам добавил академрука сверх точки: состав отличается от шаблона.
    changed = _put(project, author, route, extra_slots=[{"doc_id": APPLICATION, "slot_id": "academic_supervisor"}])
    assert changed["preset"]["differs"] == ["order", "slots"]
    assert _slots(changed)[(APPLICATION, "academic_supervisor")] == (True, "author", False)

    restored = _restore(project, author, route["id"])
    again = _restore(project, author, route["id"])

    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert _steps(body) == [["author"], ["supervisor"]]
    assert body["preset"]["differs"] == []
    people = {p["persona"]: p for step in body["steps"] for p in step}
    before = {p["persona"]: p for step in route["steps"] for p in step}
    assert people["supervisor"]["id"] == before["supervisor"]["id"]
    assert people["supervisor"]["user_id"] == supervisor.id
    assert again.status_code == 200
    [record] = _audit(stand, project, "signing_route.restore_preset")
    assert record["details"]["differs"] == ["order", "slots"]
    assert record["details"]["version"] == PRESET_VERSION


async def test__restore_preset__reviewer_forbidden__sent_route_invalid_transition(
    preset_packs: Path, stand: Stand
) -> None:
    project, author, supervisor = await _project(stand)
    for doc_id in TOPIC_DOCS:
        project.build(doc_id)
    project.png(author, "author")
    route = _create(project, author).json()
    preview = project.call(author, "POST", f"{project.routes}/{route['id']}/preview", json={}).json()
    sent = project.call(
        author,
        "POST",
        f"{project.routes}/{route['id']}/send",
        json={"expected": {d["doc_id"]: d["token"] for d in preview["docs"]}, "sign": None},
    )
    assert sent.status_code == 200, sent.text
    placements = _placements(project)

    by_reviewer = _restore(project, supervisor, route["id"])
    on_active = _restore(project, author, route["id"])
    shown = project.call(author, "GET", f"{project.routes}/{route['id']}").json()

    assert by_reviewer.status_code == 403
    assert (on_active.status_code, on_active.json()["code"]) == (409, "invalid_transition")
    # Идущий маршрут пресет не показывает и не меняет.
    assert shown["preset"] is None
    assert _placements(project) == placements


# --- «Вернуть место из шаблона» --------------------------------------------------------------------------------------


async def test__restore_place__moved_place_back_to_template__repeat_writes_nothing(
    preset_packs: Path, stand: Stand
) -> None:
    project, author, _ = await _project(stand)
    _create(project, author)
    moved = project.call(
        author,
        "PATCH",
        f"{project.base}/signatures/placements/{PROPOSAL}/supervisor",
        json={"x_mm": 20, "y_mm": 30},
    )
    assert moved.json()["origin"] == "manual"

    restored = _restore_place(project, author, PROPOSAL, "supervisor")
    again = _restore_place(project, author, PROPOSAL, "supervisor")
    unknown = _restore_place(project, author, PROPOSAL, "author")

    assert restored.status_code == 200, restored.text
    body = restored.json()
    assert (body["x_mm"], body["y_mm"], body["enabled"], body["origin"]) == (80, 139, True, "pack")
    assert [mark["format"] for mark in body["dates"]] == ["day", "month_word"]
    assert again.json() == body
    assert (unknown.status_code, unknown.json()["code"]) == (400, "unknown_slot")
    [record] = _audit(stand, project, "signature.placement_restore")
    details = record["details"]
    assert {key: details.get(key) for key in ("doc_id", "slot_id", "version", "reset", "route_id")} == {
        "doc_id": PROPOSAL,
        "slot_id": "supervisor",
        "version": PRESET_VERSION,
        "reset": [],
        "route_id": None,
    }
