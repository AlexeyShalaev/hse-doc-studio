"""Маршрут подписания глазами автора (docs/design/signing-route.md, разделы 5, 7 и 8) на настоящем сервере.

Проект КП пака hse-cs-sse, точка «Заявка на тему КП»: заявка (научрук) и заявление (автор и научрук). Подписи
картинками: научрук меняет видимый слой, поэтому после отправки его картинки придержаны, а запрос идёт его шагу.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

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

SUPERVISOR = {"name": "Петров Пётр Петрович", "role": "university"}


async def _setup(stand: Stand, *, supervisor_member: bool = True) -> tuple[Project, Person, Person]:
    author = await person(stand, "Иванов Иван Иванович")
    supervisor = await person(stand, "Петров Пётр Петрович")
    project = make_project(stand, author, supervisor=SUPERVISOR)
    if supervisor_member:
        await project.member(supervisor, "reviewer", "supervisor")
    return project, author, supervisor


def _create(project: Project, who: Person, profile_id: str = TOPIC) -> dict[str, Any]:
    resp = project.call(who, "POST", project.routes, json={"profile_id": profile_id})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _people(route: dict[str, Any]) -> list[list[tuple[str, str | None, str]]]:
    return [[(p["persona"], p["user_id"], p["membership"]) for p in step] for step in route["steps"]]


def _draft(route: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """Шаги маршрута как тело PUT: те же люди и id."""
    return [
        [{"id": p["id"], "persona": p["persona"], "user_id": p["user_id"], "invitation_id": p["invitation_id"]}]
        for step in route["steps"]
        for p in step
    ]


def _put(project: Project, who: Person, route_id: str, **body: Any) -> Any:
    payload = {"steps": [], "extra_slots": [], "deadline": None, "message": None, **body}
    return project.call(who, "PUT", f"{project.routes}/{route_id}", json=payload)


def _preview(project: Project, who: Person, route_id: str) -> dict[str, Any]:
    resp = project.call(who, "POST", f"{project.routes}/{route_id}/preview", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ready(project: Project, author: Person) -> None:
    for doc_id in TOPIC_DOCS:
        project.build(doc_id)
    project.png(author, "author")


def _send(project: Project, who: Person, route_id: str, expected: dict[str, str] | None = None) -> Any:
    if expected is None:
        expected = {d["doc_id"]: d["token"] for d in _preview(project, who, route_id)["docs"]}
    return project.call(who, "POST", f"{project.routes}/{route_id}/send", json={"expected": expected, "sign": None})


def _signatures(project: Project) -> dict[str, Any]:
    return json.loads((project.folder / ".hse-studio" / "signatures.json").read_text(encoding="utf-8"))


# --- черновик ---------------------------------------------------------------------------------------------------------


async def test__create__owner__draft_from_pack_with_people_by_persona(stand: Stand) -> None:
    project, author, supervisor = await _setup(stand)

    first = project.call(author, "POST", project.routes, json={"profile_id": TOPIC})
    again = project.call(author, "POST", project.routes, json={"profile_id": TOPIC})

    assert first.status_code == 201, first.text
    assert again.status_code == 200
    route = first.json()
    assert again.json()["id"] == route["id"]
    assert route["status"] == "draft"
    assert route["round"] == 0
    assert route["profile"]["id"] == TOPIC
    assert _people(route) == [[("author", author.id, "member")], [("supervisor", supervisor.id, "member")]]
    assert [p["name"] for step in route["steps"] for p in step] == ["Иванов Иван Иванович", "Петров Пётр Петрович"]
    by_doc = {d["doc_id"]: [(s["slot_id"], s["optional"]) for s in d["slots"]] for d in route["docs"]}
    assert by_doc == {
        "project_proposal": [("supervisor", False)],
        "topic_application": [("author", False), ("supervisor", False)],
    }
    supervisor_id = route["steps"][1][0]["id"]
    assert route["steps"][1][0]["assignments"] == [
        {"doc_id": "project_proposal", "slot_id": "supervisor"},
        {"doc_id": "topic_application", "slot_id": "supervisor"},
    ]
    assert all(
        s["participant_id"] == supervisor_id for d in route["docs"] for s in d["slots"] if s["slot_id"] == "supervisor"
    )
    assert route["events"] == []


async def test__create__unknown_checkpoint__404(stand: Stand) -> None:
    project, author, _ = await _setup(stand)

    resp = project.call(author, "POST", project.routes, json={"profile_id": "no-such-point"})

    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


async def test__create__supervisor_invited__participant_waits_for_invitation(stand: Stand) -> None:
    project, author, supervisor = await _setup(stand, supervisor_member=False)
    invited = project.call(
        author,
        "POST",
        f"{project.base}/invitations",
        json={"email": supervisor.email, "role": "reviewer", "persona": "supervisor"},
    )
    assert invited.status_code == 201, invited.text
    invitation_id = invited.json()["invitation"]["id"]

    route = _create(project, author)

    participant = route["steps"][1][0]
    assert participant["invitation_id"] == invitation_id
    assert participant["user_id"] is None
    assert participant["membership"] == "invited"
    assert participant["state"] == "invited"
    assert participant["name"] == "Петров Пётр Петрович"
    _ready(project, author)
    preview = _preview(project, author, route["id"])
    assert preview["blockers"] == []
    assert preview["can_send"] is True


async def test__create__nobody_with_persona__participant_missing_blocks_send(stand: Stand) -> None:
    project, author, _ = await _setup(stand, supervisor_member=False)
    route = _create(project, author)
    _ready(project, author)

    missing = route["steps"][1][0]
    preview = _preview(project, author, route["id"])

    assert (missing["persona"], missing["user_id"], missing["membership"], missing["name"]) == (
        "supervisor",
        None,
        "missing",
        None,
    )
    assert preview["can_send"] is False
    assert preview["blockers"] == [
        {"code": "participant_missing", "doc_id": None, "slot_id": None, "participant_id": missing["id"]}
    ]
    blocked = _send(project, author, route["id"])
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "route_blocked"
    assert blocked.json()["blockers"] == preview["blockers"]


# --- правка ---------------------------------------------------------------------------------------------------------


async def test__update__extra_slot_deadline_message__participant_added_for_optional_slot(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)

    resp = _put(
        project,
        author,
        route["id"],
        steps=_draft(route),
        extra_slots=[{"doc_id": "topic_application", "slot_id": "academic_supervisor"}],
        deadline="2026-11-15T20:59:00Z",
        message="  Прошу подписать до пятницы.  ",
    )

    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["deadline"] == "2026-11-15T20:59:00Z"
    assert updated["message"] == "Прошу подписать до пятницы."
    assert [[p["persona"] for p in step] for step in updated["steps"]] == [
        ["author"],
        ["supervisor"],
        ["academic_supervisor"],
    ]
    academic = updated["steps"][2][0]
    assert academic["membership"] == "missing"
    assert academic["assignments"] == [{"doc_id": "topic_application", "slot_id": "academic_supervisor"}]
    slots = {s["slot_id"]: s for d in updated["docs"] for s in d["slots"] if d["doc_id"] == "topic_application"}
    assert slots["academic_supervisor"]["optional"] is True
    assert slots["academic_supervisor"]["participant_id"] == academic["id"]
    assert [p["id"] for step in updated["steps"][:2] for p in step] == [
        p["id"] for step in route["steps"] for p in step
    ]
    assert project.call(author, "GET", f"{project.routes}/{route['id']}").json()["message"] == updated["message"]


async def test__update__people_in_one_step_and_removed_supervisor__slot_unassigned(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    _ready(project, author)
    author_only = [_draft(route)[0]]

    resp = _put(project, author, route["id"], steps=author_only)
    preview = _preview(project, author, route["id"])

    assert resp.status_code == 200, resp.text
    assert [[p["persona"] for p in step] for step in resp.json()["steps"]] == [["author"]]
    assert {(b["code"], b["doc_id"], b["slot_id"]) for b in preview["blockers"]} == {
        ("slot_unassigned", "project_proposal", "supervisor"),
        ("slot_unassigned", "topic_application", "supervisor"),
    }


@pytest.mark.parametrize(
    ("change", "status", "code"),
    [
        ({"extra_slots": [{"doc_id": "report", "slot_id": "author"}]}, 400, "unknown_doc"),
        ({"extra_slots": [{"doc_id": "project_proposal", "slot_id": "co_supervisor"}]}, 400, "unknown_slot"),
        ({"message": "x" * 2001}, 422, None),
        ({"steps": [[]]}, 422, None),
    ],
)
async def test__update__bad_input__rejected(
    stand: Stand, change: dict[str, Any], status: int, code: str | None
) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)

    resp = _put(project, author, route["id"], **{"steps": _draft(route), **change})

    assert resp.status_code == status, resp.text
    if code is not None:
        assert resp.json()["code"] == code


async def test__update__same_participant_twice__400(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    steps = _draft(route)

    resp = _put(project, author, route["id"], steps=[steps[0], steps[1], steps[0]])

    assert resp.status_code == 400
    assert resp.json()["code"] == "duplicate_participant"


# --- предпросмотр и отправка ------------------------------------------------------------------------------------


async def test__preview__nothing_built_and_no_author_image__blockers(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    sender = route["steps"][0][0]["id"]

    preview = _preview(project, author, route["id"])

    assert preview["can_send"] is False
    assert [d["built"] for d in preview["docs"]] == [False, False]
    assert [d["token"] for d in preview["docs"]] == [None, None]
    assert {(b["code"], b["doc_id"], b["participant_id"]) for b in preview["blockers"]} == {
        ("not_built", "project_proposal", None),
        ("not_built", "topic_application", None),
        ("sender_not_ready", None, sender),
    }


async def test__preview__ready__tokens_order_and_actions(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    _ready(project, author)

    preview = _preview(project, author, route["id"])

    assert preview["can_send"] is True
    assert preview["can_send_and_sign"] is False
    assert preview["visual_step"] == 2
    assert all(d["built"] and d["token"].startswith("build:") for d in preview["docs"])
    people = {p["persona"]: p for p in preview["participants"]}
    assert (people["author"]["step"], people["author"]["actions"], people["author"]["image_ready"]) == (1, 0, True)
    assert (people["supervisor"]["step"], people["supervisor"]["actions"]) == (2, 1)
    assert people["supervisor"]["methods"] == ["image", "detached"]
    assert people["supervisor"]["image_ready"] is False
    assert preview["sender_key"] is None
    assert project.call(author, "GET", f"{project.routes}/{route['id']}").json()["status"] == "draft"


async def test__send__author_approves_by_sending__supervisor_images_withheld_and_asked(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    _ready(project, author)
    placement = {"enabled": True, "page": 1, "x_mm": 110.0, "y_mm": 130.0, "width_mm": 40.0}
    placed = project.call(
        author, "PATCH", f"{project.base}/signatures/placements/topic_application/supervisor", json=placement
    )
    assert placed.status_code == 200, placed.text

    resp = _send(project, author, route["id"])

    assert resp.status_code == 200, resp.text
    sent = resp.json()
    assert (sent["status"], sent["phase"], sent["round"], sent["current_step"]) == ("active", "approval", 1, 2)
    assert sent["sent_by"] == {"id": author.id, "name": "Иванов Иван Иванович"}
    first, second = sent["steps"][0][0], sent["steps"][1][0]
    assert (first["state"], first["next_action"]) == ("done", "done")
    assert first["approved_at"] == sent["sent_at"]
    assert (second["state"], second["next_action"]) == ("to_approve", "approve")
    assert second["notified_at"] == sent["sent_at"]
    assert [(e["kind"], e["who"]) for e in sent["events"]] == [
        ("sent", "Иванов Иван Иванович"),
        ("approved", "Иванов Иван Иванович"),
    ]
    assert _signatures(project)["withheld"] == {"project_proposal": ["supervisor"], "topic_application": ["supervisor"]}
    plan = project.call(author, "GET", f"{project.base}/signature-plan", params={"profile_id": TOPIC}).json()
    reasons = {(d["doc_id"], s["slot_id"]): s["reason"] for d in plan["docs"] for s in d["slots"]}
    assert reasons[("topic_application", "supervisor")] == "awaiting_approval"


async def test__send__document_rebuilt_after_preview__doc_changed(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    _ready(project, author)
    expected = {d["doc_id"]: d["token"] for d in _preview(project, author, route["id"])["docs"]}
    project.build("topic_application", "v2")

    resp = _send(project, author, route["id"], expected)

    assert resp.status_code == 409
    assert resp.json()["code"] == "doc_changed"
    assert resp.json()["docs"] == ["topic_application"]
    assert project.call(author, "GET", f"{project.routes}/{route['id']}").json()["status"] == "draft"


async def test__send__active_route__invalid_transition_for_send_and_update(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    _ready(project, author)
    assert _send(project, author, route["id"]).status_code == 200

    again = _send(project, author, route["id"])
    changed = _put(project, author, route["id"], steps=_draft(route))
    archived = project.call(author, "POST", f"{project.routes}/{route['id']}/archive", json={})

    assert (again.status_code, again.json()["code"]) == (409, "invalid_transition")
    assert (changed.status_code, changed.json()["code"]) == (409, "invalid_transition")
    assert (archived.status_code, archived.json()["code"]) == (409, "invalid_transition")


async def test__send__again_within_a_minute__rate_limited(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    _ready(project, author)
    assert _send(project, author, route["id"]).status_code == 200
    assert project.call(author, "POST", f"{project.routes}/{route['id']}/cancel", json={}).status_code == 200

    resp = _send(project, author, route["id"])

    assert resp.status_code == 429
    assert resp.json()["code"] == "rate_limited"
    assert 1 <= resp.json()["retry_after"] <= 60
    assert resp.headers["Retry-After"] == str(resp.json()["retry_after"])


# --- отмена, снятие с контроля, новый маршрут --------------------------------------------------------------------


async def test__cancel_archive_then_new_route__inherits_people_and_lists_newest_first(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    _ready(project, author)
    assert _send(project, author, route["id"]).status_code == 200

    cancelled = project.call(author, "POST", f"{project.routes}/{route['id']}/cancel", json={})
    archived = project.call(author, "POST", f"{project.routes}/{route['id']}/archive", json={})
    cancel_again = project.call(author, "POST", f"{project.routes}/{route['id']}/cancel", json={})
    fresh = project.call(author, "POST", project.routes, json={"profile_id": TOPIC})
    listing = project.call(author, "GET", project.routes, params={"profile_id": TOPIC})

    assert cancelled.status_code == 200, cancelled.text
    assert (cancelled.json()["status"], cancelled.json()["phase"]) == ("cancelled", None)
    assert [e["kind"] for e in cancelled.json()["events"]] == ["sent", "approved", "cancelled"]
    # Отмена не трогает файлы: придержанные картинки остаются придержанными (5.6).
    assert _signatures(project)["withheld"]["topic_application"] == ["supervisor"]
    assert archived.json()["status"] == "archived"
    assert (cancel_again.status_code, cancel_again.json()["code"]) == (409, "invalid_transition")
    assert fresh.status_code == 201
    assert fresh.json()["id"] != route["id"]
    assert _people(fresh.json()) == _people(route)
    assert [p["approved_at"] for step in fresh.json()["steps"] for p in step] == [None, None]
    items = listing.json()["items"]
    assert [(i["id"], i["status"]) for i in items] == [(fresh.json()["id"], "draft"), (route["id"], "archived")]
    assert items[1]["steps_total"] == 2


async def test__create__after_cancel__new_draft_archives_cancelled(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    assert project.call(author, "POST", f"{project.routes}/{route['id']}/cancel", json={}).status_code == 200

    fresh = _create(project, author)

    old = project.call(author, "GET", f"{project.routes}/{route['id']}").json()
    assert old["status"] == "archived"
    assert fresh["status"] == "draft"


async def test__list__active_route__summary_with_waiting_for(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    _ready(project, author)
    assert _send(project, author, route["id"]).status_code == 200

    items = project.call(author, "GET", project.routes).json()["items"]

    assert len(items) == 1
    summary = items[0]
    assert (summary["status"], summary["phase"], summary["current_step"], summary["steps_total"]) == (
        "active",
        "approval",
        2,
        2,
    )
    assert summary["waiting_for"] == [{"name": "Петров Пётр Петрович", "persona": "supervisor"}]
    assert project.call(author, "GET", project.routes, params={"profile_id": "final"}).json() == {"items": []}


async def test__get__rebuilt_after_send__shows_computed_pause_without_writing(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    _ready(project, author)
    assert _send(project, author, route["id"]).status_code == 200
    project.build("project_proposal", "v2")

    shown = project.call(author, "GET", f"{project.routes}/{route['id']}").json()
    listed = project.call(author, "GET", project.routes).json()["items"][0]

    assert (shown["status"], shown["stop_reason"], shown["current_step"]) == ("paused", "rebuilt", None)
    assert (listed["status"], listed["stop_reason"]) == ("paused", "rebuilt")
    assert [e["kind"] for e in shown["events"]] == ["sent", "approved"]


# --- права ----------------------------------------------------------------------------------------------------------


def _calls(project: Project, route_id: str) -> list[tuple[str, str, dict[str, Any] | None]]:
    one = f"{project.routes}/{route_id}"
    return [
        ("GET", project.routes, None),
        ("POST", project.routes, {"profile_id": TOPIC}),
        ("GET", one, None),
        ("PUT", one, {"steps": [], "extra_slots": [], "deadline": None, "message": None}),
        ("POST", f"{one}/preview", {}),
        ("POST", f"{one}/send", {"expected": {}, "sign": None}),
        ("POST", f"{one}/cancel", {}),
        ("POST", f"{one}/archive", {}),
    ]


async def test__access__stranger__404_everywhere(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)
    stranger = await person(stand, "Чужой Человек")

    for method, path, body in _calls(project, route["id"]):
        resp = project.call(stranger, method, path, json=body)
        assert resp.status_code == 404, (method, path, resp.text)


async def test__access__supervisor_reviewer__reads_route_but_cannot_manage(stand: Stand) -> None:
    project, author, supervisor = await _setup(stand)
    route = _create(project, author)

    for method, path, body in _calls(project, route["id"]):
        resp = project.call(supervisor, method, path, json=body)
        expected = 200 if method == "GET" else 403
        assert resp.status_code == expected, (method, path, resp.text)
    assert project.call(author, "GET", f"{project.routes}/{route['id']}").json()["status"] == "draft"


async def test__access__reader_reads__editor_manages_in_solo_project(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    reader = await person(stand, "Читатель")
    editor = await person(stand, "Редактор")
    await project.member(reader, "reader", None)
    await project.member(editor, "editor", None)
    route = _create(project, author)

    assert project.call(reader, "GET", f"{project.routes}/{route['id']}").status_code == 200
    assert project.call(reader, "POST", f"{project.routes}/{route['id']}/cancel", json={}).status_code == 403
    assert project.call(editor, "POST", project.routes, json={"profile_id": TOPIC}).status_code == 200
    assert project.call(editor, "POST", f"{project.routes}/{route['id']}/cancel", json={}).status_code == 200


async def test__access__anonymous__401(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    route = _create(project, author)

    assert stand.client.get(f"{project.routes}/{route['id']}").status_code == 401
    assert stand.client.get(project.routes).status_code == 401


async def test__route_of_other_project__404(stand: Stand) -> None:
    project, author, _ = await _setup(stand)
    other = make_project(stand, author)
    route = _create(project, author)

    resp = other.call(author, "GET", f"{other.routes}/{route['id']}")

    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"
