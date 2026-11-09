"""Маршрут целиком через API: строки таблицы 4.4 дизайна (docs/design/signing-route.md), автор, научрук, академрук.

Автор отправляет ручками R5, подписанты действуют ручками `task`. В каждом прогоне проверяются инварианты раздела 2:
согласия по порядку шагов, картинка подписанта появляется только после его согласия, фиксация одна на маршрут и
поставленные раньше ЭП относятся к той же фиксации до самого конца.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.api.signing_routes.signer_stand import (
    APPLICATION,
    PASSPHRASE,
    PROPOSAL,
    FakeKeys,
    Trio,
    install_fake_keys,
    make_trio,
    my,
    states,
)
from tests.integration.api.signing_routes.stand import Stand

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

KEY = {"identity_id": None, "passphrase": PASSPHRASE}


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> FakeKeys:
    return install_fake_keys(monkeypatch)


def _slot_statuses(route: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {d["doc_id"]: {s["slot_id"]: s["status"] for s in d["slots"]} for d in route["docs"]}


def _assert_signatures_cover_current_freeze(trio: Trio) -> None:
    """Инвариант 3: каждая поставленная ЭП относится к текущей фиксации своего документа."""
    frozen = trio.frozen_sha()
    for doc_id, sigs in trio.signed_pdf_sha().items():
        assert set(sigs.values()) == {frozen[doc_id]}, (doc_id, sigs)


async def test__all_images__each_signer_approves_once_and_images_appear_only_after_approval(stand: Stand) -> None:
    trio = await make_trio(stand)

    sent = trio.sent()

    # Отправка это согласие автора: его картинка стоит, картинки остальных придержаны до их согласия.
    assert (sent["status"], sent["phase"], sent["current_step"]) == ("active", "approval", 2)
    assert states(sent) == ["done", "to_approve", "waiting"]
    assert trio.withheld() == {APPLICATION: ["academic_supervisor", "supervisor"], PROPOSAL: ["supervisor"]}
    assert my(trio.task(trio.supervisor)) == ("to_approve", "approve")
    assert my(trio.task(trio.academic)) == ("waiting", "wait")

    # Академрук не может опередить научрука, а научрук не согласует без картинки.
    assert trio.approve(trio.academic, expected={}).json()["code"] == "not_your_turn"
    assert trio.approve(trio.supervisor).json()["code"] == "image_required"
    uploaded = trio.image(trio.supervisor)
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["me"]["image_ready"] is True
    # Картинка загружена, но согласия ещё нет: она придержана и в плане ждёт согласования.
    assert trio.withheld()[PROPOSAL] == ["supervisor"]
    assert uploaded.json()["docs"][0]["mine"][0]["reason"] == "awaiting_approval"

    after_supervisor = trio.approved(trio.supervisor)

    assert my(after_supervisor) == ("done", "done")
    assert states(after_supervisor) == ["done", "done", "to_approve"]
    assert trio.withheld() == {APPLICATION: ["academic_supervisor"]}
    assert [slot["status"] for doc in after_supervisor["docs"] for slot in doc["mine"]] == ["signed", "signed"]

    assert trio.image(trio.academic).status_code == 200
    done = trio.approved(trio.academic)

    assert (done["route"]["status"], done["route"]["phase"]) == ("completed", "done")
    assert states(done) == ["done", "done", "done"]
    assert trio.withheld() == {}
    route = trio.route()
    assert [e["kind"] for e in route["events"]] == ["sent", "approved", "approved", "approved", "completed"]
    assert route["completed_at"] is not None
    assert _slot_statuses(route) == {
        PROPOSAL: {"supervisor": "signed"},
        APPLICATION: {"author": "signed", "supervisor": "signed", "academic_supervisor": "signed"},
    }
    # Картинки это не ЭП: фиксировать нечего.
    assert trio.frozen_sha() == {}


async def test__author_image_others_detached_with_known_keys__freeze_at_send_then_one_action_each(
    stand: Stand, keys: FakeKeys
) -> None:
    trio = await make_trio(
        stand,
        {"supervisor": "detached", "academic_supervisor": "detached"},
        plates=("supervisor", "academic_supervisor"),
    )
    keys.give(trio.supervisor, "Петров Пётр Петрович")
    keys.give(trio.academic, "Сидоров Сидор Сидорович")

    sent = trio.sent()

    # После согласия автора видимый слой никто не меняет: фиксация сразу при отправке.
    assert (sent["status"], sent["phase"], sent["current_step"]) == ("active", "signing", 2)
    assert [e["kind"] for e in sent["events"]] == ["sent", "approved", "frozen"]
    frozen = trio.frozen_sha()
    assert set(frozen) == {PROPOSAL, APPLICATION}
    task = trio.task(trio.supervisor)
    assert my(task) == ("to_approve_sign", "approve_and_sign")
    assert task["me"]["methods"] == ["detached"]
    assert {d["doc_id"]: (d["frozen"], d["token"]) for d in task["docs"]} == {
        PROPOSAL: (True, f"pdf:{frozen[PROPOSAL]}"),
        APPLICATION: (True, f"pdf:{frozen[APPLICATION]}"),
    }
    assert all(d["pdf_url"].endswith("/frozen/pdf") for d in task["docs"])
    # Академрук ждёт своего шага и после фиксации: ЭП после неё идут по порядку.
    assert my(trio.task(trio.academic)) == ("waiting", "wait")
    assert trio.approve(trio.academic, expected={}, sign=KEY).json()["code"] == "not_your_turn"

    after_supervisor = trio.approved(trio.supervisor, sign=KEY)

    assert my(after_supervisor) == ("done", "done")
    assert states(after_supervisor) == ["done", "done", "to_approve_sign"]
    _assert_signatures_cover_current_freeze(trio)

    done = trio.approved(trio.academic, sign=KEY)

    assert (done["route"]["status"], done["route"]["phase"]) == ("completed", "done")
    assert trio.events() == [
        "sent",
        "approved",
        "frozen",
        "approved",
        "signed",
        "signed",
        "approved",
        "signed",
        "completed",
    ]
    assert trio.frozen_sha() == frozen
    _assert_signatures_cover_current_freeze(trio)
    assert trio.signed_pdf_sha() == {
        PROPOSAL: {"supervisor": frozen[PROPOSAL]},
        APPLICATION: {"supervisor": frozen[APPLICATION], "academic_supervisor": frozen[APPLICATION]},
    }


async def test__all_detached_with_known_keys__send_and_sign_then_one_action_each(stand: Stand, keys: FakeKeys) -> None:
    trio = await make_trio(
        stand,
        {"author": "detached", "supervisor": "detached", "academic_supervisor": "detached"},
        images=(),
        plates=("author", "supervisor", "academic_supervisor"),
    )
    for persona, who in trio.people.items():
        keys.give(who, persona)
    preview = trio.preview()
    assert (preview["can_send_and_sign"], preview["visual_step"]) == (True, 0)
    assert [p["actions"] for p in preview["participants"]] == [1, 1, 1]

    sent = trio.sent(sign=KEY)

    assert [e["kind"] for e in sent["events"]] == ["sent", "approved", "frozen", "signed"]
    assert states(sent) == ["done", "to_approve_sign", "waiting"]
    frozen = trio.frozen_sha()

    trio.approved(trio.supervisor, sign=KEY)
    done = trio.approved(trio.academic, sign=KEY)

    assert done["route"]["status"] == "completed"
    assert trio.events().count("frozen") == 1
    assert trio.frozen_sha() == frozen
    _assert_signatures_cover_current_freeze(trio)
    assert sorted(trio.signed_pdf_sha()[APPLICATION]) == ["academic_supervisor", "author", "supervisor"]


async def test__author_and_supervisor_detached_academic_image__early_signers_sign_after_the_freeze(
    stand: Stand, keys: FakeKeys
) -> None:
    trio = await make_trio(
        stand, {"author": "detached", "supervisor": "detached"}, images=(), plates=("author", "supervisor")
    )
    keys.give(trio.author, "Иванов Иван Иванович")
    keys.give(trio.supervisor, "Петров Пётр Петрович")
    assert [p["actions"] for p in trio.preview()["participants"]] == [1, 2, 1]

    sent = trio.sent()

    # Картинка академрука ещё изменит видимый слой: фиксации нет, автор согласовал отправкой и ждёт её.
    assert (sent["phase"], sent["current_step"]) == ("approval", 2)
    assert states(sent) == ["waiting", "to_approve", "waiting"]
    assert trio.frozen_sha() == {}
    assert trio.sign(trio.author, expected={}).json()["code"] == "not_your_turn"

    first = trio.approved(trio.supervisor)

    # Первое действие научрука: согласие. Подписывать ещё нечего.
    assert my(first) == ("waiting", "wait")
    assert first["steps"][1][0]["at"] is not None
    assert trio.frozen_sha() == {}
    assert trio.sign(trio.supervisor, expected={}).json()["code"] == "not_your_turn"

    assert trio.image(trio.academic).status_code == 200
    assert trio.withheld() == {APPLICATION: ["academic_supervisor"]}
    after_academic = trio.approved(trio.academic)

    # Согласие последнего, кто меняет видимый слой, фиксирует все документы маршрута с ЭП одним разом.
    assert my(after_academic) == ("done", "done")
    assert (after_academic["route"]["phase"], after_academic["route"]["current_step"]) == ("signing", None)
    assert states(after_academic) == ["to_sign", "to_sign", "done"]
    assert trio.withheld() == {}
    frozen = trio.frozen_sha()
    assert set(frozen) == {PROPOSAL, APPLICATION}
    assert trio.events() == ["sent", "approved", "approved", "approved", "frozen"]
    # Автор и научрук получили запрос «подпишите итоговый PDF».
    assert [p["next_action"] for step in trio.route()["steps"] for p in step] == ["sign", "sign", "done"]

    # Второе действие научрука и подпись автора идут параллельно, в любом порядке.
    supervisor_task = trio.task(trio.supervisor)
    assert {d["doc_id"]: d["token"] for d in supervisor_task["docs"]} == {
        PROPOSAL: f"pdf:{frozen[PROPOSAL]}",
        APPLICATION: f"pdf:{frozen[APPLICATION]}",
    }
    second = trio.signed(trio.supervisor)
    assert my(second) == ("done", "done")
    assert second["route"]["status"] == "active"
    done = trio.signed(trio.author)

    assert (done["route"]["status"], done["route"]["phase"]) == ("completed", "done")
    assert trio.events() == [
        "sent",
        "approved",
        "approved",
        "approved",
        "frozen",
        "signed",
        "signed",
        "signed",
        "completed",
    ]
    assert trio.frozen_sha() == frozen
    _assert_signatures_cover_current_freeze(trio)


async def test__academic_detached_without_key__sets_the_key_and_signs_in_one_action(
    stand: Stand, keys: FakeKeys
) -> None:
    trio = await make_trio(
        stand, {"author": "detached", "academic_supervisor": "detached"}, images=(), plates=("author",)
    )
    keys.give(trio.author, "Иванов Иван Иванович")
    academic_key = keys.give(trio.academic, "Сидоров Сидор Сидорович")
    # Автору после отправки остаётся подписать итоговый PDF; академрук задаёт ключ и подписывает одним действием.
    assert [p["actions"] for p in trio.preview()["participants"]] == [1, 1, 1]

    sent = trio.sent()

    assert (sent["phase"], sent["current_step"]) == ("approval", 2)
    assert trio.image(trio.supervisor).status_code == 200
    after_supervisor = trio.approved(trio.supervisor)
    # Плашка академрука без данных ещё изменит видимый слой: фиксации нет.
    assert states(after_supervisor) == ["waiting", "done", "to_approve"]
    assert trio.frozen_sha() == {}

    task = trio.task(trio.academic)
    # Он последний, кто меняет видимый слой: согласие совмещается с фиксацией и подписью.
    assert my(task) == ("to_approve", "approve_and_sign")
    # В слоте данных плашки нет; страница показывает те, что даст его ключ по умолчанию.
    assert trio.state()["slots"]["academic_supervisor"]["signer"] is None
    assert task["me"]["plate"]["owner"] == "Сидоров Сидор Сидорович"
    assert task["me"]["keys"]["default_key"]["id"] == str(academic_key.id)
    assert task["docs"][0]["token"].startswith("build:")
    assert task["docs"][0]["token"].count(":") == 2

    done = trio.approved(trio.academic, sign=KEY)

    assert my(done) == ("done", "done")
    assert done["me"]["plate"] == {
        "owner": "Сидоров Сидор Сидорович",
        "kind": "openpgp",
        "cert_id": trio.academic.id.upper()[:16],
    }
    assert states(done) == ["to_sign", "done", "done"]
    frozen = trio.frozen_sha()
    assert trio.events() == ["sent", "approved", "approved", "approved", "frozen", "signed"]

    completed = trio.signed(trio.author)

    assert completed["route"]["status"] == "completed"
    assert trio.frozen_sha() == frozen
    assert trio.events().count("frozen") == 1
    _assert_signatures_cover_current_freeze(trio)
