"""«Пропустить» участника маршрута на настоящем сервере (docs/design/signing-route.md, 13.6, 13.7 и 13.8).

Пропуск это сценарий автора: права `SUBMISSION_CREATE`, коды 13.6, событие и запись журнала, уведомление пропущенному
и поля `skip`, `optional`, `extra` в ответах автора и подписанта.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.api.signing_routes.signer_stand import APPLICATION, PROPOSAL, Trio, make_trio
from tests.integration.api.signing_routes.stand import TOPIC, Person, Stand
from tests.integration.api.signing_routes.watch_stand import drain, notifications

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

ACADEMIC = "academic_supervisor"


def _code(resp: Any) -> tuple[int, str | None]:
    return resp.status_code, resp.json().get("code") if resp.content else None


def _mark(trio: Trio, *, optional: bool = True, slot_id: str = ACADEMIC) -> Any:
    path = f"{trio.project.base}/signatures/optional/{APPLICATION}/{slot_id}"
    return trio.call(trio.author, "PUT", path, json={"profile_id": TOPIC, "optional": optional})


def _skip(trio: Trio, participant: str, who: Person | None = None) -> Any:
    return trio.call(who or trio.author, "POST", f"{trio.url}/participants/{participant}/skip", json={})


def _by_persona(route: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["persona"]: p for step in route["steps"] for p in step}


async def _academic_turn(stand: Stand, *, optional: bool = True) -> Trio:
    """Маршрут отправлен, подписи академрука необязательны (если `optional`), очередь дошла до академрука."""
    trio = await make_trio(stand, images=("author", "supervisor"))
    trio.sent()
    if optional:
        assert _mark(trio).status_code == 200
    trio.approved(trio.supervisor)
    return trio


async def test__skip__academic_turn_with_optional_slot__skipped_route_completes_and_everyone_is_told(
    stand: Stand,
) -> None:
    trio = await _academic_turn(stand)
    before = _by_persona(trio.route())[ACADEMIC]
    assert before["skip"] == {"available": True, "blocker": None, "keeps_marks": [], "refreezes": []}
    assert before["skipped_at"] is None
    academic_id = before["id"]

    resp = _skip(trio, academic_id)
    drain(stand)

    assert resp.status_code == 200, resp.text
    route = resp.json()
    academic = _by_persona(route)[ACADEMIC]
    assert (academic["state"], academic["next_action"]) == ("skipped", "done")
    assert academic["skipped_at"] is not None
    # Маршрут завершён: пропуск показывается только у идущего.
    assert academic["skip"] is None
    assert route["status"] == "completed"
    slots = {s["slot_id"]: s for doc in route["docs"] for s in doc["slots"] if doc["doc_id"] == APPLICATION}
    assert (slots[ACADEMIC]["status"], slots[ACADEMIC]["extra"], slots[ACADEMIC]["optional"]) == (
        "skipped",
        True,
        True,
    )
    assert (slots["supervisor"]["extra"], slots["supervisor"]["optional"]) == (False, False)
    skipped = [e for e in route["events"] if e["kind"] == "skipped"]
    assert [(e["who"], e["participant_id"]) for e in skipped] == [("Иванов Иван Иванович", academic_id)]
    # Состояние подписей: пропуск записан с маршрутом и раундом.
    record = trio.state()["skipped"][APPLICATION][ACADEMIC]
    assert (record["profile_id"], record["route_id"], record["round"]) == (TOPIC, trio.route_id, 1)
    # Пропущенный получает уведомление, автор о завершении.
    told = notifications(stand, trio, ACADEMIC, "signing_skipped")
    assert [(n["payload"]["actor_name"], n["payload"]["ref_id"], n["payload"]["profile_id"]) for n in told] == [
        ("Иванов Иван Иванович", trio.route_id, TOPIC)
    ]
    assert told[0]["payload"]["excerpt"]
    assert notifications(stand, trio, "author", "signing_skipped") == []
    assert len(notifications(stand, trio, "author", "signing_completed")) == 1
    audit = stand.admin().get("/api/admin/audit", params={"target": trio.project.id, "limit": 200}).json()["items"]
    entries = [e for e in audit if e["action"] == "signing_route.skip"]
    assert [(e["actor_id"], e["details"]["participant_id"], e["details"]["slots"]) for e in entries] == [
        (trio.author.id, academic_id, [{"doc_id": APPLICATION, "slot_id": ACADEMIC}])
    ]
    assert (entries[0]["details"]["kept_marks"], entries[0]["details"]["refrozen"]) == ([], [])


async def test__skip__repeated__done(stand: Stand) -> None:
    trio = await _academic_turn(stand)
    academic_id = _by_persona(trio.route())[ACADEMIC]["id"]
    assert _skip(trio, academic_id).status_code == 200

    again = _skip(trio, academic_id)

    # Маршрут завершился: пропускать некого.
    assert _code(again) == (409, "invalid_transition")


async def test__skip__refusals__not_turn_required_slots_no_slots_and_unknown(stand: Stand) -> None:
    trio = await _academic_turn(stand)
    people = _by_persona(trio.route())
    supervisor_id, academic_id = people["supervisor"]["id"], people[ACADEMIC]["id"]
    # Научрук уже согласовал: его пропустить нельзя, он закончил.
    done = _skip(trio, supervisor_id)

    assert _code(done) == (409, "participant_not_skippable")
    assert done.json()["reason"] == "done"
    assert done.json()["slots"] == []
    assert _skip(trio, "not-an-uuid").status_code == 404
    assert _skip(trio, "00000000-0000-4000-8000-000000000001").status_code == 404
    assert academic_id


async def test__skip__not_his_turn__and_required_slots(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"))
    trio.sent()
    assert _mark(trio).status_code == 200
    people = _by_persona(trio.route())
    academic, supervisor = people[ACADEMIC], people["supervisor"]

    early = _skip(trio, academic["id"])
    required = _skip(trio, supervisor["id"])

    assert _code(early) == (409, "participant_not_skippable")
    assert early.json()["reason"] == "not_turn"
    assert academic["skip"]["blocker"] == "not_turn"
    assert _code(required) == (409, "participant_not_skippable")
    assert required.json()["reason"] == "required_slots"
    assert {(s["doc_id"], s["slot_id"]) for s in required.json()["slots"]} == {
        (PROPOSAL, "supervisor"),
        (APPLICATION, "supervisor"),
    }
    assert supervisor["skip"]["blocker"] == "required_slots"


async def test__skip__slot_not_optional__required_slots(stand: Stand) -> None:
    trio = await _academic_turn(stand, optional=False)
    academic = _by_persona(trio.route())[ACADEMIC]

    resp = _skip(trio, academic["id"])

    assert academic["skip"]["blocker"] == "required_slots"
    assert _code(resp) == (409, "participant_not_skippable")
    assert resp.json()["reason"] == "required_slots"
    assert [(s["doc_id"], s["slot_id"]) for s in resp.json()["slots"]] == [(APPLICATION, ACADEMIC)]


async def test__skip__approver_without_slots__no_slots(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="approver")
    trio.sent()
    trio.approved(trio.supervisor)
    academic = _by_persona(trio.route())[ACADEMIC]

    resp = _skip(trio, academic["id"])

    assert academic["skip"]["blocker"] == "no_slots"
    assert _code(resp) == (409, "participant_not_skippable")
    assert resp.json()["reason"] == "no_slots"


async def test__skip__draft_route__invalid_transition(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"))
    academic = _by_persona(trio.route())[ACADEMIC]

    resp = _skip(trio, academic["id"])

    assert _code(resp) == (409, "invalid_transition")
    assert _by_persona(trio.route())[ACADEMIC]["skip"] is None


async def test__skip__only_for_those_who_manage_the_route(stand: Stand) -> None:
    trio = await _academic_turn(stand)
    academic_id = _by_persona(trio.route())[ACADEMIC]["id"]

    by_reviewer = _skip(trio, academic_id, trio.supervisor)
    seen_by_reviewer = _by_persona(trio.route(trio.supervisor))[ACADEMIC]

    assert by_reviewer.status_code == 403
    assert seen_by_reviewer["skip"] is None
    assert _by_persona(trio.route())[ACADEMIC]["state"] == "to_approve"


async def test__task__optional_places_are_marked_and_a_skipped_signer_sees_it(stand: Stand) -> None:
    trio = await _academic_turn(stand)

    mine = trio.task(trio.academic)
    academic_id = mine["me"]["participant_id"]
    skipped = _skip(trio, academic_id)
    after = trio.task(trio.academic)

    assert (mine["me"]["optional"], mine["me"]["state"]) == (True, "to_approve")
    assert [(s["slot_id"], s["optional"], s["status"]) for d in mine["docs"] for s in d["mine"]] == [
        (ACADEMIC, True, "pending")
    ]
    assert skipped.status_code == 200
    assert (after["me"]["optional"], after["me"]["state"], after["me"]["next_action"]) == (False, "skipped", "done")
    assert [(s["slot_id"], s["status"]) for d in after["docs"] for s in d["mine"]] == [(ACADEMIC, "skipped")]
    assert [p["state"] for step in after["steps"] for p in step][-1] == "skipped"


async def test__task__required_places__not_optional(stand: Stand) -> None:
    trio = await _academic_turn(stand, optional=False)

    mine = trio.task(trio.academic)

    assert mine["me"]["optional"] is False
    assert [s["optional"] for d in mine["docs"] for s in d["mine"]] == [False]
