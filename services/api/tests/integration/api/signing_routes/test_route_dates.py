"""Метки даты на документе под маршрутом на настоящем сервере (docs/design/signing-route.md, 14.5 и 14.6).

Живой случай владельца: маршрут «Заявка на тему КП» на шаге 3 из 3 ждёт академрука (его подпись необязательна),
научрук согласовал «Описание проекта» картинкой до появления меток, ЭП на документе нет. Автор добавляет три метки
даты («день», «месяц словом», «год двумя цифрами») слоту научрука: маршрут идёт дальше, подписи не сбрасываются,
дата дозаполняется из согласия научрука, в PDF день его согласия по Москве. То же на завершённом маршруте. Затем
правка с ЭП над зафиксированным PDF: 409 `resets_signatures`, подтверждение, повторный запрос подписи.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from hse_doc_studio.use_cases.signing_route.dates import RouteDatesEditing
from pypdf import PdfReader
from sqlalchemy import text

from tests.integration.api.signing_routes.signer_stand import (
    APPLICATION,
    NAMES,
    PASSPHRASE,
    PROPOSAL,
    FakeKeys,
    Trio,
    install_fake_keys,
    make_trio,
    my,
    states,
)
from tests.integration.api.signing_routes.stand import TOPIC, Stand
from tests.integration.api.signing_routes.watch_stand import drain, notifications, project_changed

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

KEY = {"identity_id": None, "passphrase": PASSPHRASE}
ACADEMIC = "academic_supervisor"
# Согласие научрука в 22:30 UTC 12 ноября: по Москве это уже 13 ноября, 01:30.
APPROVED_AT = "2026-11-12T22:30:00+00:00"
THREE = [
    {"id": None, "page": 1, "x_mm": 120.0, "y_mm": 250.0, "width_mm": 8.0, "height_mm": 5.0, "format": "day"},
    {"id": None, "page": 1, "x_mm": 132.0, "y_mm": 250.0, "width_mm": 24.0, "height_mm": 5.0, "format": "month_word"},
    {"id": None, "page": 1, "x_mm": 162.0, "y_mm": 250.0, "width_mm": 6.0, "height_mm": 5.0, "format": "year_short"},
]


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> FakeKeys:
    return install_fake_keys(monkeypatch)


def _code(resp: Any) -> tuple[int, str | None]:
    return resp.status_code, resp.json().get("code") if resp.content else None


def _put_dates(trio: Trio, doc_id: str, slot_id: str, body: dict[str, Any]) -> Any:
    return trio.call(
        trio.author, "PUT", f"{trio.project.base}/signatures/placements/{doc_id}/{slot_id}/dates", json=body
    )


async def _approved_at(trio: Trio, persona: str, at: str) -> None:
    """Время согласия участника в базе: как будто он согласовал в `at`."""
    async with trio.stand.sessions.use() as db:
        await db.execute(
            text(
                "UPDATE signing_route_participants"
                " SET approval = jsonb_set(approval, '{at}', to_jsonb(CAST(:at AS text))) WHERE persona = :persona"
            ),
            {"at": at, "persona": persona},
        )


def _pdf_text(trio: Trio, doc_id: str) -> str:
    resp = trio.call(trio.author, "GET", f"{trio.project.base}/docs/{doc_id}/pdf/signed")
    assert resp.status_code == 200, resp.text
    return " ".join(page.extract_text() for page in PdfReader(io.BytesIO(resp.content)).pages)


def _audit(trio: Trio, action: str) -> list[dict[str, Any]]:
    audit = trio.stand.admin().get("/api/admin/audit", params={"target": trio.project.id, "limit": 200}).json()
    return [e for e in audit["items"] if e["action"] == action]


def _assert_date_from_approval(trio: Trio, resp: Any) -> None:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [m["text"] for m in body["dates"]] == ["13", "ноября", "26"]
    assert body["signed_at"] == {"at": APPROVED_AT, "source": "approval"}
    placement = trio.state()["placements"][PROPOSAL]["supervisor"]
    assert placement["signed_at"]["source"] == "approval"
    assert placement["signed_at"]["token"].startswith("build:")
    text_ = _pdf_text(trio, PROPOSAL)
    assert "13" in text_
    assert "ноября" in text_
    assert "26" in text_


async def test__live_form__going_route_waits_for_academic__supervisor_dates_backfilled_nothing_stops(
    stand: Stand,
) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"))
    trio.sent()
    optional = trio.call(
        trio.author,
        "PUT",
        f"{trio.project.base}/signatures/optional/{APPLICATION}/{ACADEMIC}",
        json={"profile_id": TOPIC, "optional": True},
    )
    assert optional.status_code == 200, optional.text
    trio.approved(trio.supervisor)
    await _approved_at(trio, "supervisor", APPROVED_AT)
    before = trio.route()
    assert (before["status"], before["current_step"], states(before)) == ("active", 3, ["done", "done", "to_approve"])
    signatures_before = (trio.state().get("detached", {}), trio.state().get("frozen", {}), trio.withheld())
    requests_before = notifications(stand, trio, "supervisor", "signing_request")

    resp = _put_dates(trio, PROPOSAL, "supervisor", {"dates": THREE})
    # Хуки и периодическая сверка после правки маршрут не останавливают: снимок её принял.
    drain(stand)
    project_changed(stand, trio)

    _assert_date_from_approval(trio, resp)
    route = trio.route()
    assert (route["status"], route["phase"], route["current_step"], route["stop_reason"]) == (
        "active",
        "approval",
        3,
        None,
    )
    assert states(route) == ["done", "done", "to_approve"]
    assert route["events"][-1]["kind"] == "marks_edited"
    assert route["events"][-1]["who"] == NAMES["author"]
    assert (trio.state().get("detached", {}), trio.state().get("frozen", {}), trio.withheld()) == signatures_before
    assert my(trio.task(trio.academic)) == ("to_approve", "approve")
    # Пропустить академрука по-прежнему можно (раздел 13): метки маршрут не сломали.
    academic = next(p for step in route["steps"] for p in step if p["persona"] == ACADEMIC)
    assert academic["skip"]["available"] is True
    supervisor_task = trio.task(trio.supervisor)
    mine = next(d for d in supervisor_task["docs"] if d["doc_id"] == PROPOSAL)["mine"][0]
    assert [m["text"] for m in mine["dates"]] == ["13", "ноября", "26"]
    assert [(m["page"], m["x_mm"], m["width_mm"], m["height_mm"]) for m in mine["dates"]] == [
        (1, 120.0, 8.0, 5.0),
        (1, 132.0, 24.0, 5.0),
        (1, 162.0, 6.0, 5.0),
    ]
    [record] = _audit(trio, "signing_route.marks_edit")
    assert (record["actor_id"], record["details"]["doc_id"], record["details"]["slot_id"]) == (
        trio.author.id,
        PROPOSAL,
        "supervisor",
    )
    assert (record["details"]["marks"], record["details"]["reset"]) == (3, [])
    assert notifications(stand, trio, "supervisor", "signing_request") == requests_before


async def test__live_form__completed_route__dates_backfilled_route_stays_completed(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    assert trio.approved(trio.supervisor)["route"]["status"] == "completed"
    await _approved_at(trio, "supervisor", APPROVED_AT)

    resp = _put_dates(trio, PROPOSAL, "supervisor", {"dates": THREE})
    drain(stand)
    project_changed(stand, trio)

    _assert_date_from_approval(trio, resp)
    route = trio.route()
    assert (route["status"], route["phase"], route["stop_reason"]) == ("completed", "done", None)
    assert trio.events()[-2:] == ["completed", "marks_edited"]
    # Метки можно и убрать тем же сценарием: маршрут по-прежнему завершён.
    cleared = _put_dates(trio, PROPOSAL, "supervisor", {"dates": []})
    drain(stand)
    assert cleared.status_code == 200, cleared.text
    assert trio.route()["status"] == "completed"


async def test__marks_on_a_held_document__no_submission_right__route_locked(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Правку размещений вправе делать и тот, кто не отправляет маршрут: его правка меток идёт мимо сценария, 409."""
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    before = trio.state()

    async def no_right(self: RouteDatesEditing, project_id: Any) -> bool:
        return False

    monkeypatch.setattr(RouteDatesEditing, "_manages", no_right)
    resp = _put_dates(trio, PROPOSAL, "supervisor", {"dates": THREE})

    assert _code(resp) == (409, "route_locked")
    assert trio.state() == before


async def test__manual_date_on_a_route_pair__date_from_route__other_slot_on_the_document_allowed(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"))
    trio.sent()
    manual = {"dates": [THREE[0]], "signed_at": {"date": "2026-11-13"}}

    on_route = _put_dates(trio, APPLICATION, "supervisor", manual)
    # Слот соруководителя в маршрут не входит: его ручная дата идёт сценарием маршрута, как любая правка меток.
    beside = _put_dates(trio, APPLICATION, "co_supervisor", manual)
    drain(stand)

    assert _code(on_route) == (409, "date_from_route")
    assert beside.status_code == 200, beside.text
    assert beside.json()["signed_at"] == {"at": "2026-11-13", "source": "manual"}
    assert trio.route()["status"] == "active"
    assert trio.events()[-1] == "marks_edited"


async def test__esign_over_frozen_pdf__409_resets_signatures__confirm_refreezes_and_asks_to_sign_again(
    stand: Stand, keys: FakeKeys
) -> None:
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    keys.give(trio.supervisor, NAMES["supervisor"])
    trio.sent()
    done = trio.approved(trio.supervisor, sign=KEY)
    assert done["route"]["status"] == "completed"
    frozen = trio.frozen_sha()
    before = trio.state()
    requests_before = notifications(stand, trio, "supervisor", "signing_request")

    refused = _put_dates(trio, APPLICATION, "supervisor", {"dates": THREE})

    assert _code(refused) == (409, "resets_signatures")
    assert refused.json()["resets"] == [{"doc_id": APPLICATION, "slot_id": "supervisor", "name": NAMES["supervisor"]}]
    assert trio.state() == before
    assert trio.route()["status"] == "completed"

    confirmed = _put_dates(trio, APPLICATION, "supervisor", {"dates": THREE, "confirm_reset": True})
    drain(stand)

    assert confirmed.status_code == 200, confirmed.text
    assert None not in [m["text"] for m in confirmed.json()["dates"]]
    assert confirmed.json()["signed_at"]["source"] == "approval"
    route = trio.route()
    assert (route["status"], route["phase"]) == ("active", "signing")
    assert my(trio.task(trio.supervisor)) == ("to_sign", "sign")
    assert trio.frozen_sha()[APPLICATION] != frozen[APPLICATION]
    assert trio.frozen_sha()[PROPOSAL] == frozen[PROPOSAL]
    assert set(trio.signed_pdf_sha().get(APPLICATION, {})) == set()
    assert [e["kind"] for e in route["events"]][-2:] == ["marks_edited", "frozen"]
    [record] = _audit(trio, "signing_route.marks_edit")
    assert record["details"]["reset"] == [{"doc_id": APPLICATION, "slot_id": "supervisor"}]
    # Запрос «Подпишите итоговый PDF» пришёл заново: новый ключ повтора с отпечатком нового B.
    requests = notifications(stand, trio, "supervisor", "signing_request")
    assert len(requests) == len(requests_before) + 1
    assert requests[0]["payload"]["outcome"] == "sign"

    signed = trio.signed(trio.supervisor)

    assert signed["route"]["status"] == "completed"
    assert set(trio.signed_pdf_sha()[APPLICATION].values()) == {trio.frozen_sha()[APPLICATION]}


async def test__dates_for_a_pending_esign_signer__warned_now__his_approval_refreezes_and_re_requests(
    stand: Stand, keys: FakeKeys
) -> None:
    """Метки даты академруку, который ещё не согласовал, делают его меняющим видимый слой (14.4): B зафиксируют
    заново после его согласия, поэтому сброс ЭП научрука подтверждают сейчас, а запрос научруку приходит, когда
    перефиксация случится."""
    trio = await make_trio(
        stand,
        {"supervisor": "detached", ACADEMIC: "detached"},
        plates=("supervisor", ACADEMIC),
    )
    keys.give(trio.supervisor, NAMES["supervisor"])
    keys.give(trio.academic, NAMES[ACADEMIC])
    trio.sent()
    trio.approved(trio.supervisor, sign=KEY)
    assert my(trio.task(trio.academic)) == ("to_approve_sign", "approve_and_sign")
    frozen = trio.frozen_sha()

    refused = _put_dates(trio, APPLICATION, ACADEMIC, {"dates": THREE})
    confirmed = _put_dates(trio, APPLICATION, ACADEMIC, {"dates": THREE, "confirm_reset": True})
    drain(stand)

    assert _code(refused) == (409, "resets_signatures")
    assert [r["slot_id"] for r in refused.json()["resets"]] == ["supervisor"]
    assert confirmed.status_code == 200, confirmed.text
    assert [m["text"] for m in confirmed.json()["dates"]] == [None, None, None]
    # Пока академрук не согласовал, B тот же и подпись научрука на месте; фиксация ждёт академрука.
    assert trio.frozen_sha() == frozen
    route = trio.route()
    assert (route["status"], route["phase"]) == ("active", "approval")
    asked_before = len(notifications(stand, trio, "supervisor", "signing_request"))

    done = trio.approved(trio.academic, sign=KEY)

    assert my(done) == ("done", "done")
    assert trio.frozen_sha()[APPLICATION] != frozen[APPLICATION]
    assert trio.state()["placements"][APPLICATION][ACADEMIC]["signed_at"]["source"] == "approval"
    assert my(trio.task(trio.supervisor)) == ("to_sign", "sign")
    assert len(notifications(stand, trio, "supervisor", "signing_request")) == asked_before + 1
    assert trio.signed(trio.supervisor)["route"]["status"] == "completed"
