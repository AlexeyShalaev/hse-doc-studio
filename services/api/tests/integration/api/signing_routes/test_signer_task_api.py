"""Задача подписанта и её действия (docs/design/signing-route.md, разделы 5.5, 6.10, 7 и 8) на настоящем сервере.

Каждая ручка `task`: что видит участник, отказы не участнику и не в свою очередь, сверка отпечатков, картинка,
плашка, способ, подпись ключом Студии, возврат, гонка двух подписантов и другие входы подписи (6.10).
"""

from __future__ import annotations

import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.enums import DetachedFormat, DetachedOrigin, DetachedVerdict
from hse_doc_studio.core.signing_route.repositories import StaleRouteError
from hse_doc_studio.core.value_objects import DetachedSignature
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow
from hse_doc_studio.infra.db.repositories.signing_routes import SqlSigningRouteRepository
from hse_doc_studio.use_cases.signatures.attach_detached_signature import (
    AttachDetachedSignatureInput,
    AttachDetachedSignatureOutput,
    AttachDetachedSignatureUC,
)
from hse_doc_studio.use_cases.signing_route import author as author_module
from sqlalchemy import update

from tests.fakes.signer_profile import make_png, make_self_signed
from tests.integration.api.signing_routes.signer_stand import (
    APPLICATION,
    PASSPHRASE,
    PNG,
    PROPOSAL,
    FakeKeys,
    Trio,
    install_fake_keys,
    make_trio,
    my,
    states,
)
from tests.integration.api.signing_routes.stand import Person, Stand, person

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

KEY = {"identity_id": None, "passphrase": PASSPHRASE}


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> FakeKeys:
    return install_fake_keys(monkeypatch)


def _code(resp: Any) -> tuple[int, str]:
    return resp.status_code, resp.json().get("code")


def _signer_calls(trio: Trio, who: Person) -> list[Any]:
    """Каждое действие подписанта от имени `who` с правдоподобным телом."""
    return [
        trio.approve(who, expected={}),
        trio.sign(who, expected={}),
        trio.give_back(who),
        trio.image(who),
        trio.plate_key(who, str(uuid4())),
        trio.plate_file(who, make_self_signed().cert_pem),
    ]


# --- что видит участник -----------------------------------------------------------------------------------------------


async def test__task__participant_sees_own_slots_other_marks_and_route_progress(stand: Stand) -> None:
    trio = await make_trio(stand)
    trio.sent()

    task = trio.task(trio.supervisor)

    route = task["route"]
    assert (route["id"], route["project"]["id"], route["profile"]["id"]) == (
        trio.route_id,
        trio.project.id,
        "topic-approval",
    )
    assert (route["status"], route["phase"], route["round"], route["current_step"]) == ("active", "approval", 1, 2)
    assert (route["sender"], route["message"]) == ("Иванов Иван Иванович", "Прошу подписать заявление до пятницы.")
    assert [[(p["name"], p["persona"], p["state"], p["me"]) for p in step] for step in task["steps"]] == [
        [("Иванов Иван Иванович", "author", "done", False)],
        [("Петров Пётр Петрович", "supervisor", "to_approve", True)],
        [("Сидоров Сидор Сидорович", "academic_supervisor", "waiting", False)],
    ]
    assert task["steps"][0][0]["at"] == route["sent_at"]
    me = task["me"]
    assert (me["state"], me["next_action"], me["method"], me["methods"]) == (
        "to_approve",
        "approve",
        "image",
        ["image", "detached"],
    )
    assert (me["image_ready"], me["image_url"], me["plate"]) == (False, None, None)
    assert me["keys"] == {"server_keys_allowed": False, "default_key": None}
    proposal, application = task["docs"]
    assert (proposal["doc_id"], application["doc_id"]) == (PROPOSAL, APPLICATION)
    assert proposal["pdf_url"] == f"/api/v1/projects/{trio.project.id}/docs/{PROPOSAL}/pdf/signed"
    assert proposal["token"].startswith("build:")
    assert proposal["frozen"] is False
    assert proposal["others"] == []
    # Свой слот: место из пака, высота по пропорции рамки под картинку, причина плана.
    assert proposal["mine"] == [
        {
            "slot_id": "supervisor",
            "label": {"ru": "Научный руководитель", "en": "Supervisor"},
            "page": 1,
            "x_mm": 110.0,
            "y_mm": 130.0,
            "width_mm": 40.0,
            "height_mm": 16.0,
            "mark": "png",
            "status": "pending",
            "reason": "awaiting_approval",
        }
    ]
    # Чужие слоты с местом, но без причины плана.
    assert [(s["slot_id"], s["status"], s["mark"], s["x_mm"]) for s in application["others"]] == [
        ("author", "signed", "png", 160.0),
        ("academic_supervisor", "pending", "png", 165.0),
    ]
    assert all("reason" not in s for s in application["others"])
    author_id = trio.route()["steps"][0][0]["id"]
    assert [(e["kind"], e["who"], e["participant_id"]) for e in task["events"]] == [
        ("sent", "Иванов Иван Иванович", None),
        ("approved", "Иванов Иван Иванович", author_id),
    ]

    mine = trio.task(trio.author)

    # Автор видит только заявление: на заявке его слотов нет. Его очередь прошла, отпечатков нет.
    assert [d["doc_id"] for d in mine["docs"]] == [APPLICATION]
    assert my(mine) == ("done", "done")
    assert mine["docs"][0]["token"] is None
    assert [s["slot_id"] for s in mine["docs"][0]["mine"]] == ["author"]


async def test__task__approver_without_slots__sees_every_route_document_and_approves_in_turn(stand: Stand) -> None:
    trio = await make_trio(stand, academic="approver")
    trio.sent()
    trio.image(trio.supervisor)

    before = trio.task(trio.academic)

    assert [(d["doc_id"], d["mine"]) for d in before["docs"]] == [(PROPOSAL, []), (APPLICATION, [])]
    assert [s["slot_id"] for s in before["docs"][1]["others"]] == ["author", "supervisor"]
    assert (before["me"]["method"], before["me"]["methods"], before["me"]["image_ready"]) == (None, [], False)
    assert my(before) == ("waiting", "wait")
    assert _code(trio.approve(trio.academic, expected={})) == (409, "not_your_turn")
    # Согласующему нечего ставить на документ.
    assert _code(trio.image(trio.academic)) == (409, "not_your_turn")

    trio.approved(trio.supervisor)
    task = trio.task(trio.academic)
    assert my(task) == ("to_approve", "approve")
    assert all(d["token"].startswith("build:") for d in task["docs"])
    done = trio.approved(trio.academic)

    assert done["route"]["status"] == "completed"
    assert my(done) == ("done", "done")


async def test__task__draft_route__participant_waits(stand: Stand) -> None:
    trio = await make_trio(stand)

    task = trio.task(trio.supervisor)

    assert (task["route"]["status"], task["route"]["sender"], task["route"]["sent_at"]) == ("draft", None, None)
    assert my(task) == ("waiting", "wait")
    assert _code(trio.approve(trio.supervisor, expected={})) == (409, "not_your_turn")


# --- доступ ---------------------------------------------------------------------------------------------------------


async def test__task__not_a_participant__404_on_every_endpoint(stand: Stand) -> None:
    trio = await make_trio(stand, academic="none")
    trio.sent()
    reader = await person(stand, "Читатель")
    await trio.project.member(reader, "reviewer", None)
    stranger = await person(stand, "Посторонний")

    for who in (reader, stranger):
        get = trio.call(who, "GET", f"{trio.url}/task")
        assert _code(get) == (404, "not_found"), who
        assert trio.call(who, "GET", f"{trio.url}/task/image").status_code == 404
        for resp in _signer_calls(trio, who):
            assert resp.status_code == 404, (who, resp.request.url, resp.text)
    # Ничего не изменилось: научрук по-прежнему ждёт своей очереди согласовать.
    assert my(trio.task(trio.supervisor)) == ("to_approve", "approve")
    assert trio.events() == ["sent", "approved"]


async def test__task__anonymous__401(stand: Stand) -> None:
    trio = await make_trio(stand, academic="none")

    resp = stand.client.get(f"{trio.url}/task")

    assert resp.status_code == 401


async def test__task__route_of_another_project__404(stand: Stand) -> None:
    trio = await make_trio(stand, academic="none")
    other = await make_trio(stand, academic="none")

    resp = trio.call(trio.supervisor, "GET", f"{trio.project.routes}/{other.route_id}/task")

    assert _code(resp) == (404, "not_found")


async def test__approve__sign_right_taken_away__403(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    # Читатель с персоной остаётся участником маршрута, но подписывать слоты уже не вправе.
    async with stand.sessions.use() as db:
        await db.execute(
            update(ProjectMemberRow)
            .where(
                ProjectMemberRow.project_id == UUID(trio.project.id),
                ProjectMemberRow.principal_id == trio.supervisor.id,
            )
            .values(role="reader")
        )

    resp = trio.approve(trio.supervisor)

    assert resp.status_code == 403
    assert my(trio.task(trio.supervisor)) == ("to_approve", "approve")


# --- очередь --------------------------------------------------------------------------------------------------------


async def test__actions__out_of_turn__not_your_turn_and_nothing_changes(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"))
    trio.sent()

    # Академрук до своего шага не может ничего, в том числе заранее положить картинку или вернуть документ.
    assert [_code(resp) for resp in _signer_calls(trio, trio.academic)] == [(409, "not_your_turn")] * 6
    # Научрук в свою очередь согласует, но подписывать ему нечего.
    assert _code(trio.sign(trio.supervisor, expected={})) == (409, "not_your_turn")
    trio.approved(trio.supervisor)
    # Кто закончил, тот больше не действует.
    assert [_code(resp) for resp in _signer_calls(trio, trio.supervisor)] == [(409, "not_your_turn")] * 6
    assert [_code(resp) for resp in _signer_calls(trio, trio.author)] == [(409, "not_your_turn")] * 6
    assert trio.events() == ["sent", "approved", "approved"]


async def test__actions__route_cancelled__not_your_turn(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    tokens = trio.tokens(trio.supervisor)
    assert trio.call(trio.author, "POST", f"{trio.url}/cancel", json={}).status_code == 200

    resp = trio.approve(trio.supervisor, expected=tokens)

    assert _code(resp) == (409, "not_your_turn")
    task = trio.task(trio.supervisor)
    assert (task["route"]["status"], my(task)) == ("cancelled", ("waiting", "wait"))


# --- отпечатки ------------------------------------------------------------------------------------------------------


async def test__approve__stale_or_missing_expected__doc_changed_with_documents(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    tokens = trio.tokens(trio.supervisor)

    stale = trio.approve(trio.supervisor, expected={**tokens, PROPOSAL: "build:" + "0" * 64})
    missing = trio.approve(trio.supervisor, expected={})

    assert _code(stale) == (409, "doc_changed")
    assert stale.json()["docs"] == [PROPOSAL]
    assert missing.json()["docs"] == [PROPOSAL, APPLICATION]
    assert my(trio.task(trio.supervisor)) == ("to_approve", "approve")
    assert trio.events() == ["sent", "approved"]


async def test__approve__document_rebuilt_after_the_page_was_opened__doc_changed_and_route_paused(
    stand: Stand,
) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    seen = trio.tokens(trio.supervisor)
    trio.project.build(PROPOSAL, "v2")

    resp = trio.approve(trio.supervisor, expected=seen)

    assert _code(resp) == (409, "doc_changed")
    assert resp.json()["docs"] == [PROPOSAL]
    # Действие подписанта заметило изменение: маршрут остановлен и записан остановленным.
    route = trio.route()
    assert (route["status"], route["stop_reason"]) == ("paused", "rebuilt")
    assert [(e["kind"], e["reason"]) for e in route["events"]][-1] == ("paused", "rebuilt")
    task = trio.task(trio.supervisor)
    assert (task["route"]["status"], task["route"]["stop_reason"], my(task)) == (
        "paused",
        "rebuilt",
        ("waiting", "wait"),
    )
    assert _code(trio.approve(trio.supervisor, expected=trio.tokens(trio.supervisor))) == (409, "not_your_turn")
    # Картинка научрука так и не появилась, картинка автора осталась: его документ не менялся.
    assert trio.withheld() == {APPLICATION: ["supervisor"], PROPOSAL: ["supervisor"]}


# --- картинка -------------------------------------------------------------------------------------------------------


async def test__image__stays_withheld_until_approval_and_can_be_previewed(stand: Stand) -> None:
    trio = await make_trio(stand, academic="none")
    trio.sent()
    assert trio.call(trio.supervisor, "GET", f"{trio.url}/task/image").status_code == 404

    bad = trio.image(trio.supervisor, b"not a png")
    empty = trio.image(trio.supervisor, b"")
    ok = trio.image(trio.supervisor, PNG)

    assert _code(bad) == (400, "invalid_file")
    assert _code(empty) == (400, "invalid_file")
    assert ok.status_code == 200, ok.text
    me = ok.json()["me"]
    assert me["image_ready"] is True
    assert me["image_url"] == f"/api/v1/projects/{trio.project.id}/signing-routes/{trio.route_id}/task/image"
    preview = trio.call(trio.supervisor, "GET", me["image_url"])
    assert (preview.status_code, preview.headers["content-type"], preview.content) == (200, "image/png", PNG)
    # Высота рамки теперь по пропорциям загруженной картинки (120x40).
    assert ok.json()["docs"][0]["mine"][0]["height_mm"] == pytest.approx(40.0 / 3, abs=0.01)
    assert trio.withheld() == {APPLICATION: ["supervisor"], PROPOSAL: ["supervisor"]}
    assert my(ok.json()) == ("to_approve", "approve")
    # В профиль картинка без `remember` не попала.
    profile = stand.client.get("/api/v1/account/signer-profile", headers=trio.supervisor.headers).json()
    assert profile["image"] is None


async def test__image__remember__saved_to_the_signer_profile(stand: Stand) -> None:
    trio = await make_trio(stand, academic="none")
    trio.sent()
    png = make_png(200, 50)

    resp = trio.image(trio.supervisor, png, remember=True)

    assert resp.status_code == 200, resp.text
    profile = stand.client.get("/api/v1/account/signer-profile", headers=trio.supervisor.headers).json()
    assert (profile["image"]["width_px"], profile["image"]["height_px"]) == (200, 50)
    saved = stand.client.get("/api/v1/account/signer-profile/image", headers=trio.supervisor.headers)
    assert saved.content == png


# --- плашка и способ ------------------------------------------------------------------------------------------------


async def test__plate_key__last_visible_change__documents_freeze_and_the_plate_is_locked(
    stand: Stand, keys: FakeKeys
) -> None:
    trio = await make_trio(stand, {"supervisor": "detached"}, academic="none")
    key = keys.give(trio.supervisor, "Петров Пётр Петрович")
    trio.sent()
    before = trio.task(trio.supervisor)
    # Плашка без данных ещё изменит видимый слой: фиксации нет. Страница видит ключ по умолчанию.
    assert my(before) == ("to_approve", "approve_and_sign")
    assert before["me"]["keys"]["default_key"]["id"] == str(key.id)
    assert before["me"]["plate"]["owner"] == "Петров Пётр Петрович"
    assert trio.frozen_sha() == {}

    foreign = trio.plate_key(trio.supervisor, str(uuid4()))
    malformed = trio.plate_key(trio.supervisor, "not-a-key")
    resp = trio.plate_key(trio.supervisor, str(key.id))

    assert _code(foreign) == (409, "key_not_found")
    assert _code(malformed) == (409, "key_not_found")
    assert resp.status_code == 200, resp.text
    task = resp.json()
    # Больше видимый слой никто не меняет: документы зафиксированы, в ответе уже новые отпечатки.
    assert my(task) == ("to_approve_sign", "approve_and_sign")
    frozen = trio.frozen_sha()
    assert {d["doc_id"]: d["token"] for d in task["docs"]} == {
        PROPOSAL: f"pdf:{frozen[PROPOSAL]}",
        APPLICATION: f"pdf:{frozen[APPLICATION]}",
    }
    assert task["me"]["plate"] == {
        "owner": "Петров Пётр Петрович",
        "kind": "openpgp",
        "cert_id": trio.supervisor.id.upper()[:16],
    }
    assert task["me"]["methods"] == ["detached"]
    assert trio.state()["slots"]["supervisor"]["signer"]["signer_id"] == trio.supervisor.id.upper()
    assert trio.events() == ["sent", "approved", "frozen"]
    # После фиксации плашку, картинку и способ менять нельзя: это сбросило бы зафиксированный PDF.
    assert _code(trio.plate_key(trio.supervisor, str(key.id))) == (409, "visible_layer_final")
    assert _code(trio.plate_file(trio.supervisor, make_self_signed().cert_pem)) == (409, "visible_layer_final")
    assert _code(trio.image(trio.supervisor)) == (409, "visible_layer_final")
    assert _code(trio.approve(trio.supervisor, method="image")) == (409, "method_not_allowed")
    assert trio.frozen_sha() == frozen

    done = trio.approved(trio.supervisor, sign=KEY)

    assert done["route"]["status"] == "completed"
    assert trio.events() == ["sent", "approved", "frozen", "approved", "signed", "signed", "completed"]
    assert trio.frozen_sha() == frozen


async def test__plate_file__certificate_sets_the_plate__private_key_and_garbage_rejected(stand: Stand) -> None:
    trio = await make_trio(stand, {"supervisor": "detached"}, academic="none")
    trio.sent()
    cert = make_self_signed("Петров Пётр Петрович", serial=0x1A2B)

    with_key = trio.plate_file(trio.supervisor, cert.key_pem + cert.cert_pem)
    garbage = trio.plate_file(trio.supervisor, b"hello")
    assert trio.frozen_sha() == {}
    resp = trio.plate_file(trio.supervisor, cert.cert_pem)

    assert _code(with_key) == (400, "invalid_file")
    assert _code(garbage) == (400, "invalid_file")
    assert resp.status_code == 200, resp.text
    task = resp.json()
    assert (task["me"]["plate"]["owner"], task["me"]["plate"]["kind"]) == ("Петров Пётр Петрович", "x509")
    assert my(task) == ("to_approve_sign", "approve_and_sign")
    assert set(trio.frozen_sha()) == {PROPOSAL, APPLICATION}
    # Высота рамки своей плашки посчитана по её вёрстке: подпись, сертификат, владелец, срок.
    assert task["docs"][0]["mine"][0]["mark"] == "plate"
    assert task["docs"][0]["mine"][0]["height_mm"] > 10


async def test__profile_certificate__plate_known_in_advance_and_filled_at_the_freeze(
    stand: Stand, keys: FakeKeys
) -> None:
    trio = await make_trio(stand, {"supervisor": "detached"}, profile_certs=("supervisor",), academic="none")
    keys.give(trio.supervisor, "Петров Пётр Петрович")
    preview = trio.preview()
    assert [(p["persona"], p["plate_ready"]) for p in preview["participants"]] == [
        ("author", True),
        ("supervisor", True),
    ]
    # Отправка это согласие автора: после неё видимый слой никто не меняет.
    assert preview["visual_step"] == 0

    sent = trio.sent()

    # Данные плашки научрука известны из его профиля: после согласия автора фиксация сразу.
    assert [e["kind"] for e in sent["events"]] == ["sent", "approved", "frozen"]
    signer = trio.state()["slots"]["supervisor"]["signer"]
    assert (signer["kind"], signer["owner"]) == ("x509", "Петров Пётр Петрович")
    task = trio.task(trio.supervisor)
    assert my(task) == ("to_approve_sign", "approve_and_sign")
    assert task["me"]["plate"]["kind"] == "x509"
    # Ключ Студии не тот, что на плашке: отказ до записи согласия.
    refused = trio.approve(trio.supervisor, sign=KEY)
    assert _code(refused) == (403, "forbidden")
    assert my(trio.task(trio.supervisor)) == ("to_approve_sign", "approve_and_sign")


async def test__approve__method_changed_to_detached__plate_from_the_signing_key(stand: Stand, keys: FakeKeys) -> None:
    trio = await make_trio(stand, academic="none")
    keys.give(trio.supervisor, "Петров Пётр Петрович")
    trio.sent()
    assert trio.withheld() == {APPLICATION: ["supervisor"], PROPOSAL: ["supervisor"]}
    placed = {doc_id: trio.state()["placements"][doc_id]["supervisor"] for doc_id in (PROPOSAL, APPLICATION)}
    assert all(p["width_mm"] < 70 for p in placed.values())

    not_accepted = trio.approve(trio.supervisor, method="pades")
    done = trio.approved(trio.supervisor, method="detached", sign=KEY)

    # Точка принимает картинку и открепленную ЭП; PAdES выбрать нельзя.
    assert _code(not_accepted) == (409, "method_not_allowed")
    assert done["route"]["status"] == "completed"
    assert (done["me"]["method"], done["me"]["methods"]) == ("detached", ["detached"])
    state = trio.state()
    assert state["slots"]["supervisor"]["sign_mode"] == "detached_text"
    assert state["slots"]["supervisor"]["signer"]["owner"] == "Петров Пётр Петрович"
    # Рамка картинки узка для плашки: место выросло до 70 мм до фиксации, правый край на месте.
    for doc_id in (PROPOSAL, APPLICATION):
        before, after = placed[doc_id], state["placements"][doc_id]["supervisor"]
        assert after["width_mm"] == 70
        assert after["x_mm"] + after["width_mm"] == pytest.approx(before["x_mm"] + before["width_mm"])
    # Слот больше не картинка: придерживать нечего, плашка вошла в фиксацию.
    assert trio.withheld() == {}
    assert trio.events() == ["sent", "approved", "approved", "frozen", "signed", "signed", "completed"]


async def test__approve__visible_method_without_place__not_offered_and_refused(stand: Stand) -> None:
    """Академрук подписывает заявление PAdES без метки, места его подписи автор не разместил (помехи нет). Картинку
    и плашку ставить некуда: их не предлагают, а смена на них отказ с понятной причиной (раздел 6.3)."""
    trio = await make_trio(stand, {"academic_supervisor": "pades"})
    placement = f"{trio.project.base}/signatures/placements/{APPLICATION}/academic_supervisor"
    assert trio.call(trio.author, "PATCH", placement, json={"enabled": False}).status_code == 200
    # Научрук картинкой после академрука: пока он не согласовал, фиксации нет, академрук выбирает способ.
    people = {p["persona"]: p for p in trio.steps()}
    trio.put(
        [[people["author"]], [people["academic_supervisor"]], [people["supervisor"]]],
        [{"doc_id": APPLICATION, "slot_id": "academic_supervisor"}],
    )
    trio.sent()

    task = trio.task(trio.academic)
    refused = trio.approve(trio.academic, method="image")
    plate = trio.approve(trio.academic, method="detached")

    assert my(task) == ("to_approve", "approve")
    # Необязательный слот точка не ограничивает, но из трёх способов места не нужно только PAdES без метки.
    assert (task["me"]["method"], task["me"]["methods"]) == ("pades", ["pades"])
    assert _code(refused) == (409, "method_not_allowed")
    assert _code(plate) == (409, "method_not_allowed")
    detail = refused.json()["detail"]
    assert "места" in detail or "place" in detail
    assert trio.state()["slots"]["academic_supervisor"]["sign_mode"] == "crypto_invisible"
    assert trio.events() == ["sent", "approved"]

    # Своим способом, без метки, согласовать можно.
    done = trio.approved(trio.academic)
    assert my(done)[0] != "to_approve"
    assert trio.events() == ["sent", "approved", "approved"]


async def test__approve__method_changed_without_plate_data__plate_required_and_nothing_written(stand: Stand) -> None:
    trio = await make_trio(stand, academic="none")
    trio.sent()
    before = trio.state()

    resp = trio.approve(trio.supervisor, method="detached")

    assert _code(resp) == (409, "plate_required")
    assert trio.state() == before
    assert my(trio.task(trio.supervisor)) == ("to_approve", "approve")


async def test__approve__no_key_in_request__default_key_fills_the_plate(stand: Stand, keys: FakeKeys) -> None:
    trio = await make_trio(stand, {"supervisor": "detached"}, academic="none")
    keys.give(trio.supervisor, "Петров Пётр Петрович")
    trio.sent()

    task = trio.approved(trio.supervisor)

    # Согласие без подписи ключом (КриптоПро, готовая подпись): документы зафиксированы, ждём его ЭП.
    frozen = trio.frozen_sha()
    assert my(task) == ("to_sign", "sign")
    assert {d["doc_id"]: d["token"] for d in task["docs"]} == {
        PROPOSAL: f"pdf:{frozen[PROPOSAL]}",
        APPLICATION: f"pdf:{frozen[APPLICATION]}",
    }
    assert trio.state()["slots"]["supervisor"]["signer"]["owner"] == "Петров Пётр Петрович"
    assert trio.events() == ["sent", "approved", "approved", "frozen"]


# --- подпись ключом Студии -----------------------------------------------------------------------------------------


async def test__approve_and_sign__key_refusals_come_before_the_approval(stand: Stand, keys: FakeKeys) -> None:
    trio = await make_trio(
        stand,
        {"supervisor": "detached", "academic_supervisor": "detached"},
        plates=("supervisor", "academic_supervisor"),
    )
    keys.give(trio.supervisor, "Петров Пётр Петрович")
    trio.sent()
    assert my(trio.task(trio.supervisor)) == ("to_approve_sign", "approve_and_sign")

    no_passphrase = trio.approve(trio.supervisor, sign={"identity_id": None, "passphrase": None})
    foreign_key = trio.approve(trio.supervisor, sign={"identity_id": str(uuid4()), "passphrase": PASSPHRASE})

    assert _code(no_passphrase) == (400, "passphrase_required")
    assert _code(foreign_key) == (409, "key_not_found")
    assert my(trio.task(trio.supervisor)) == ("to_approve_sign", "approve_and_sign")
    assert trio.events() == ["sent", "approved", "frozen"]


async def test__approve_and_sign__signing_fails_after_the_approval__signer_left_to_sign(
    stand: Stand, keys: FakeKeys
) -> None:
    trio = await make_trio(
        stand,
        {"supervisor": "detached", "academic_supervisor": "detached"},
        plates=("supervisor", "academic_supervisor"),
    )
    keys.give(trio.supervisor, "Петров Пётр Петрович")
    trio.sent()
    keys.broken = True

    failed = trio.approve(trio.supervisor, sign=KEY)

    assert _code(failed) == (400, "sign_failed")
    assert "Bad passphrase" in failed.json()["detail"]
    task = trio.task(trio.supervisor)
    # Согласие записано, подпись нет: он согласовал после фиксации и держит свой шаг до подписи.
    assert my(task) == ("to_sign", "sign")
    assert states(task) == ["done", "to_sign", "waiting"]
    assert trio.events() == ["sent", "approved", "frozen", "approved"]
    assert _code(trio.sign(trio.supervisor)) == (400, "sign_failed")
    assert _code(trio.sign(trio.supervisor, passphrase=None)) == (400, "passphrase_required")
    keys.broken = False

    done = trio.signed(trio.supervisor)

    assert my(done) == ("done", "done")
    assert states(done) == ["done", "done", "to_approve_sign"]
    assert trio.events() == ["sent", "approved", "frozen", "approved", "signed", "signed"]


async def test__approve_without_key__after_freeze__to_sign_with_pdf_tokens_and_step_is_held(
    stand: Stand, keys: FakeKeys
) -> None:
    trio = await make_trio(
        stand,
        {"supervisor": "detached", "academic_supervisor": "detached"},
        plates=("supervisor", "academic_supervisor"),
    )
    keys.give(trio.supervisor, "Петров Пётр Петрович")
    trio.sent()
    frozen = trio.frozen_sha()

    task = trio.approved(trio.supervisor)

    assert my(task) == ("to_sign", "sign")
    assert {d["doc_id"]: d["token"] for d in task["docs"]} == {
        PROPOSAL: f"pdf:{frozen[PROPOSAL]}",
        APPLICATION: f"pdf:{frozen[APPLICATION]}",
    }
    # Следующий шаг ждёт его подписи: согласие после фиксации считается вместе с ней.
    assert states(task) == ["done", "to_sign", "waiting"]
    assert _code(trio.sign(trio.supervisor, expected={PROPOSAL: "pdf:" + "0" * 64})) == (409, "doc_changed")


async def test__sign_with_studio_key__server_keys_forbidden__403_and_nothing_recorded(stand: Stand) -> None:
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    trio.sent()

    refused = trio.approve(trio.supervisor, sign=KEY)
    plate = trio.plate_key(trio.supervisor, str(uuid4()))

    # На установке закрытые ключи на сервере запрещены (по умолчанию): подписать ключом Студии нельзя.
    assert _code(refused) == (403, "server_keys_forbidden")
    assert plate.status_code in (403, 409)
    task = trio.task(trio.supervisor)
    assert my(task) == ("to_approve_sign", "approve_and_sign")
    assert task["me"]["keys"] == {"server_keys_allowed": False, "default_key": None}


# --- возврат --------------------------------------------------------------------------------------------------------


async def test__return__comment_required__route_returned_and_author_notified(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(author_module, "SEND_INTERVAL", timedelta(0))
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()

    empty = trio.give_back(trio.supervisor, "   ")
    too_long = trio.give_back(trio.supervisor, "я" * 2001)
    resp = trio.give_back(trio.supervisor, "  Уточните цель проекта  ")

    assert empty.status_code == 422
    assert too_long.status_code == 422
    assert resp.status_code == 200, resp.text
    task = resp.json()
    assert (task["route"]["status"], task["route"]["stop_reason"], my(task)) == (
        "returned",
        "returned",
        ("returned", "wait"),
    )
    supervisor_id = task["me"]["participant_id"]
    assert [(e["kind"], e["comment"], e["reason"], e["participant_id"]) for e in task["events"]][-1] == (
        "returned",
        "Уточните цель проекта",
        "returned",
        supervisor_id,
    )
    route = trio.route()
    assert (route["status"], route["stop_reason"]) == ("returned", "returned")
    assert route["events"][-1]["comment"] == "Уточните цель проекта"
    inbox = stand.client.get("/api/v1/account/notifications", headers=trio.author.headers).json()
    returned = [n for n in inbox["items"] if n["kind"] == "signing_returned"]
    assert [(n["payload"]["actor_name"], n["payload"]["excerpt"]) for n in returned] == [
        ("Петров Пётр Петрович", "Уточните цель проекта")
    ]
    assert _code(trio.approve(trio.supervisor, expected={})) == (409, "not_your_turn")
    assert _code(trio.give_back(trio.supervisor)) == (409, "not_your_turn")

    # Автор отправляет заново, ничего не меняя: у научрука снова его очередь, уже во втором раунде.
    again = trio.sent()

    assert (again["status"], again["round"]) == ("active", 2)
    task = trio.task(trio.supervisor)
    assert (task["route"]["round"], my(task)) == (2, ("to_approve", "approve"))
    assert trio.approved(trio.supervisor)["route"]["status"] == "completed"


# --- гонка подписантов ----------------------------------------------------------------------------------------------


async def _parallel_step(stand: Stand) -> Trio:
    """Научрук и академрук одним шагом: оба согласуют параллельно."""
    trio = await make_trio(stand, images=("author", "supervisor", "academic_supervisor"))
    author, supervisor, academic = trio.steps()
    trio.put([[author], [supervisor, academic]], [{"doc_id": APPLICATION, "slot_id": "academic_supervisor"}])
    trio.sent()
    return trio


async def test__two_signers_of_one_step__approve_at_the_same_time__both_recorded(stand: Stand) -> None:
    trio = await _parallel_step(stand)
    assert states(trio.route()) == ["done", "to_approve", "to_approve"]
    expected = {who.id: trio.tokens(who) for who in (trio.supervisor, trio.academic)}
    results: dict[str, Any] = {}

    def approve(who: Person) -> None:
        results[who.id] = trio.approve(who, expected=expected[who.id])

    threads = [threading.Thread(target=approve, args=(who,)) for who in (trio.supervisor, trio.academic)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    # Строка маршрута под блокировкой: действия идут по очереди, ни одно не затирает другое. Проигравший гонку
    # получает 409 (`stale_route` или `doc_changed`: видимый слой уже другой) и повторяет со свежей задачей.
    for who in (trio.supervisor, trio.academic):
        resp = results[who.id]
        if resp.status_code != 200:
            assert _code(resp) in {(409, "stale_route"), (409, "doc_changed")}, resp.text
            trio.approved(who)
    route = trio.route()
    assert route["status"] == "completed"
    assert states(route) == ["done", "done", "done"]
    assert sorted(e["kind"] for e in route["events"]) == ["approved", "approved", "approved", "completed", "sent"]
    assert trio.withheld() == {}


async def test__approve__route_rewritten_in_parallel__stale_route_then_retry_succeeds(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    trio = await _parallel_step(stand)
    real_save = SqlSigningRouteRepository.save
    calls = {"n": 0}

    async def racing_save(self: SqlSigningRouteRepository, route: Any, *, events: Any = ()) -> Any:
        # Как если бы маршрут успели перезаписать между чтением и записью: версия в базе уже другая.
        calls["n"] += 1
        if calls["n"] == 1:
            raise StaleRouteError(route.id)
        return await real_save(self, route, events=events)

    monkeypatch.setattr(SqlSigningRouteRepository, "save", racing_save)

    lost = trio.approve(trio.supervisor)

    assert _code(lost) == (409, "stale_route")
    # Запись маршрута откатилась, согласия нет. Картинку сценарий уже открыл в файлах проекта, а снимок маршрута
    # остался прежним: следующий расчёт видит чужое изменение видимого слоя и останавливает маршрут (5.5, 5.8).
    assert trio.events() == ["sent", "approved"]
    assert trio.withheld() == {APPLICATION: ["academic_supervisor"]}
    route = trio.route()
    assert (route["status"], route["stop_reason"]) == ("paused", "marks_changed")

    refused = trio.approve(trio.supervisor, expected={})

    # Первое же действие записывает остановку и снова придерживает картинку без согласия.
    assert _code(refused) == (409, "doc_changed")
    assert trio.events() == ["sent", "approved", "paused"]
    assert trio.withheld() == {APPLICATION: ["academic_supervisor", "supervisor"], PROPOSAL: ["supervisor"]}


# --- другие входы подписи (6.10) --------------------------------------------------------------------------------------


def _fake_attach(verdict: DetachedVerdict) -> Any:
    """Двойник загрузки готовой подписи: запись открепленной подписи над текущей фиксацией с нужным вердиктом."""

    async def execute(
        self: AttachDetachedSignatureUC, inp: AttachDetachedSignatureInput
    ) -> AttachDetachedSignatureOutput:
        from hse_doc_studio.api.config import settings  # noqa: PLC0415

        folder = settings.data_dir / "projects" / str(inp.project_id)
        state = self._signature_repo.get_state(folder)
        signature = DetachedSignature(
            file=f".hse-studio/detached/{inp.doc_id}/{inp.slot_id}.asc",
            format=DetachedFormat.openpgp,
            origin=DetachedOrigin.uploaded,
            pdf_sha256=state.frozen[inp.doc_id].sha256,
            verdict=verdict,
            signer="Петров Пётр Петрович",
            signer_id="ABCDEF",
            added_at=datetime.now(UTC).isoformat(),
        )
        detached = {**state.detached.get(inp.doc_id, {}), inp.slot_id: signature}
        self._signature_repo.save_state(folder, replace(state, detached={**state.detached, inp.doc_id: detached}))
        return AttachDetachedSignatureOutput(signature=signature)

    return execute


def _upload(trio: Trio, who: Person, doc_id: str, slot_id: str = "supervisor") -> Any:
    return trio.call(
        who,
        "POST",
        f"{trio.project.base}/docs/{doc_id}/detached/{slot_id}",
        files={"file": ("signature.asc", b"-----BEGIN PGP SIGNATURE-----", "application/pgp-signature")},
    )


async def test__ready_signature__only_the_participant_in_turn_to_sign__route_recalculated(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(AttachDetachedSignatureUC, "execute", _fake_attach(DetachedVerdict.valid))
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    trio.sent()

    # Владелец не подписывает за научрука, пока маршрут идёт; сам научрук сначала согласует.
    assert _code(_upload(trio, trio.author, PROPOSAL)) == (409, "not_your_turn")
    assert _code(_upload(trio, trio.supervisor, PROPOSAL)) == (409, "not_your_turn")
    assert trio.state().get("detached", {}) == {}
    assert my(trio.approved(trio.supervisor)) == ("to_sign", "sign")

    first = _upload(trio, trio.supervisor, PROPOSAL)

    assert first.status_code == 200, first.text
    route = trio.route()
    supervisor_id = route["steps"][1][0]["id"]
    assert (route["status"], [e["kind"] for e in route["events"]][-1]) == ("active", "signed")
    assert route["events"][-1]["participant_id"] == supervisor_id
    assert route["events"][-1]["who"] == "Петров Пётр Петрович"

    second = _upload(trio, trio.supervisor, APPLICATION)

    assert second.status_code == 200, second.text
    done = trio.route()
    assert done["status"] == "completed"
    assert [e["kind"] for e in done["events"]] == [
        "sent",
        "approved",
        "frozen",
        "approved",
        "signed",
        "signed",
        "completed",
    ]


async def test__ready_signature__invalid_verdict__slot_not_signed_and_route_still_waits(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(AttachDetachedSignatureUC, "execute", _fake_attach(DetachedVerdict.invalid))
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    trio.sent()
    trio.approved(trio.supervisor)

    resp = _upload(trio, trio.supervisor, PROPOSAL)

    assert resp.status_code == 200, resp.text
    task = trio.task(trio.supervisor)
    assert my(task) == ("to_sign", "sign")
    assert [(s["status"], s["reason"]) for s in task["docs"][0]["mine"]] == [("invalid", "invalid_signature")]
    assert trio.events() == ["sent", "approved", "frozen", "approved"]
