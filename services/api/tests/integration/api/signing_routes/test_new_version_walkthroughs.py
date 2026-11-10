"""Версия на подписи через API: строки таблицы 12.6 дизайна (docs/design/signing-route.md, раздел 12).

Отправка снимает версию на подписи каждого документа, правка и пересборка маршрут не останавливают, подписант
видит снятую версию, «Отправить новую версию» снимает только изменившиеся документы и сохраняет согласия по
остальным, отмена снимает версии, пакет собирается из версии на подписи.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.use_cases.signing_route import author as author_module
from pypdf import PdfReader

from tests.integration.api.signing_routes.signer_stand import APPLICATION, PROPOSAL, Trio, make_trio, my, states
from tests.integration.api.signing_routes.stand import TOPIC, Person, Stand
from tests.integration.api.signing_routes.test_route_audit import _audit

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]


@pytest.fixture(autouse=True)
def _no_send_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    # Новая версия идёт следом за отправкой: ограничение «раз в минуту» здесь не проверяется.
    monkeypatch.setattr(author_module, "SEND_INTERVAL", timedelta(0))


def _pinned(trio: Trio) -> dict[str, dict[str, Any]]:
    return dict(trio.state().get("pinned", {}))


def _working_sha(trio: Trio, doc_id: str) -> str:
    doc = trio.call(trio.author, "GET", f"{trio.project.base}/documents/{doc_id}").json()
    return hashlib.sha256((trio.project.folder / doc["output_file"]).read_bytes()).hexdigest()


def _doc(body: dict[str, Any], doc_id: str) -> dict[str, Any]:
    return next(d for d in body["docs"] if d["doc_id"] == doc_id)


def _pdf_text(data: bytes) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


def _notifications(trio: Trio, who: Person) -> list[dict[str, Any]]:
    resp = trio.call(who, "GET", "/api/v1/account/notifications")
    assert resp.status_code == 200, resp.text
    return list(resp.json()["items"])


def _route_audit(trio: Trio) -> list[dict[str, Any]]:
    return _audit(trio, "signing_route")


def _send_version(trio: Trio, note: str | None = None) -> dict[str, Any]:
    preview = trio.preview()
    expected = {d["doc_id"]: d["token"] for d in preview["docs"]}
    body: dict[str, Any] = {"expected": expected, "sign": None}
    if note is not None:
        body["note"] = note
    resp = trio.call(trio.author, "POST", f"{trio.url}/send", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _all_approved(stand: Stand) -> Trio:
    trio = await make_trio(stand, images=("author", "supervisor", "academic_supervisor"))
    trio.sent()
    trio.approved(trio.supervisor)
    trio.approved(trio.academic)
    assert trio.route()["status"] == "completed"
    return trio


async def test__send__pins_every_document__rebuild_does_not_stop_and_signer_sees_the_version(stand: Stand) -> None:
    trio = await make_trio(stand)

    sent = trio.sent()

    pinned = _pinned(trio)
    assert set(pinned) == {APPLICATION, PROPOSAL}
    for doc_id, version in pinned.items():
        assert (version["route_id"], version["round"]) == (trio.route_id, 1)
        assert version["sha256"] == _working_sha(trio, doc_id)
        assert (trio.project.folder / version["path"]).is_file()
        assert _doc(sent, doc_id)["sent"]["sha256"] == version["sha256"]
        assert _doc(sent, doc_id)["changed"] is False
    assert sent["changed_docs"] == []
    sent_event = next(e for e in sent["events"] if e["kind"] == "sent")
    assert sent_event["changed_docs"] is None

    # Правка и пересборка: маршрут идёт дальше, у документа «есть изменения после отправки».
    trio.project.build(PROPOSAL, "v2")
    route = trio.route()

    assert (route["status"], route["stop_reason"]) == ("active", None)
    assert route["changed_docs"] == [PROPOSAL]
    assert (_doc(route, PROPOSAL)["changed"], _doc(route, APPLICATION)["changed"]) == (True, False)
    [summary] = trio.call(trio.author, "GET", trio.project.routes).json()["items"]
    assert (summary["docs"], summary["changed_docs"]) == ([PROPOSAL, APPLICATION], [PROPOSAL])

    # Подписант видит версию на подписи, а не рабочую сборку, и о правках не знает.
    task = trio.task(trio.supervisor)
    proposal = _doc(task, PROPOSAL)
    assert proposal["sent_at"] is not None
    assert (proposal["changed"], proposal["changed_since_mine"], task["route"]["new_version"]) == (None, False, False)
    pdf = trio.call(trio.supervisor, "GET", proposal["pdf_url"])
    assert pdf.status_code == 200, pdf.text
    assert "v1" in _pdf_text(pdf.content)
    assert "v2" not in _pdf_text(pdf.content)
    # Автор управляет маршрутом: ему расхождение видно и на странице подписи.
    assert _doc(trio.task(trio.author), APPLICATION)["changed"] is False

    # Согласие научрука по версии на подписи проходит, хотя рабочая сборка другая.
    assert trio.image(trio.supervisor).status_code == 200
    approved = trio.approved(trio.supervisor)
    assert approved["route"]["status"] == "active"
    assert my(approved) == ("done", "done")


async def test__new_version__only_changed_document_repinned__approvals_on_the_other_stay(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"))
    trio.sent()
    trio.approved(trio.supervisor)
    before = _pinned(trio)
    trio.project.build(PROPOSAL, "v2")

    preview = trio.preview()

    assert preview["can_send"] is True
    assert {d["doc_id"]: d["change"] for d in preview["docs"]} == {PROPOSAL: "changed", APPLICATION: "same"}
    assert _doc(preview, PROPOSAL)["token"] == f"build:{_working_sha(trio, PROPOSAL)}"
    assert _doc(preview, PROPOSAL)["sent"]["sha256"] == before[PROPOSAL]["sha256"]
    keeps = {p["persona"]: p["keeps_approval"] for p in preview["participants"]}
    assert keeps == {"author": True, "supervisor": False, "academic_supervisor": False}

    resent = _send_version(trio, note="  Исправил цель проекта в предложении.  ")

    after = _pinned(trio)
    assert after[APPLICATION] == before[APPLICATION]
    assert (after[PROPOSAL]["round"], after[PROPOSAL]["sha256"]) == (2, _working_sha(trio, PROPOSAL))
    assert (resent["status"], resent["round"], resent["message"]) == (
        "active",
        2,
        "Исправил цель проекта в предложении.",
    )
    assert resent["changed_docs"] == []
    sent_event = [e for e in resent["events"] if e["kind"] == "sent"][-1]
    assert sent_event["changed_docs"] == [PROPOSAL]
    # Научрук согласует заново только изменившееся предложение; на заявлении его картинка остаётся.
    assert states(resent) == ["done", "to_approve", "waiting"]
    assert trio.withheld().get(APPLICATION, []) == ["academic_supervisor"]
    assert trio.withheld()[PROPOSAL] == ["supervisor"]

    task = trio.task(trio.supervisor)
    assert task["route"]["new_version"] is True
    assert (_doc(task, APPLICATION)["token"], _doc(task, APPLICATION)["changed_since_mine"]) == (None, False)
    assert _doc(task, PROPOSAL)["changed_since_mine"] is True
    assert _doc(task, PROPOSAL)["token"] is not None
    request = next(n for n in _notifications(trio, trio.supervisor) if n["payload"]["new_version"])
    assert request["kind"] == "signing_request"

    approved = trio.approved(trio.supervisor)
    assert my(approved) == ("done", "done")
    assert trio.withheld() == {APPLICATION: ["academic_supervisor"]}


async def test__completed_route__new_version__lost_approvals_notified_and_nothing_changed_refused(
    stand: Stand,
) -> None:
    trio = await _all_approved(stand)

    # Без изменений новую версию отправлять нечего: предпросмотр не даёт кнопку, отправка отвечает 409.
    preview = trio.preview()
    assert preview["can_send"] is False
    assert [b["code"] for b in preview["blockers"]] == ["nothing_changed"]
    refused = trio.call(trio.author, "POST", f"{trio.url}/send", json={"expected": {}, "sign": None})
    assert (refused.status_code, refused.json()["code"]) == (409, "nothing_changed")

    # Завершённый маршрут правкой не останавливается.
    trio.project.build(APPLICATION, "v2")
    assert (trio.route()["status"], trio.route()["changed_docs"]) == ("completed", [APPLICATION])

    resent = _send_version(trio)

    assert (resent["status"], resent["round"]) == ("active", 2)
    assert states(resent) == ["done", "to_approve", "waiting"]
    # Академрук уже согласовал заявление: его очередь ещё не настала, во «Входящие» приходит новая версия.
    kinds = [n["kind"] for n in _notifications(trio, trio.academic)]
    assert "signing_new_version" in kinds
    assert "signing_new_version" not in [n["kind"] for n in _notifications(trio, trio.supervisor)]
    assert "signing_new_version" not in [n["kind"] for n in _notifications(trio, trio.author)]
    sends = [e for e in _route_audit(trio) if e["action"] == "signing_route.send"]
    assert [(e["details"]["new_version"], e["details"]["changed_docs"]) for e in sends] == [
        (False, []),
        (True, [APPLICATION]),
    ]
    assert [v["doc_id"] for v in sends[-1]["details"]["versions"]] == [APPLICATION]


async def test__cancel__removes_pins__resend_pins_again(stand: Stand) -> None:
    trio = await make_trio(stand)
    trio.sent()
    files = [trio.project.folder / version["path"] for version in _pinned(trio).values()]

    cancelled = trio.call(trio.author, "POST", f"{trio.url}/cancel", json={})

    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert _pinned(trio) == {}
    assert not any(path.exists() for path in files)
    [record] = [e for e in _route_audit(trio) if e["action"] == "signing_route.cancel"]
    assert record["details"]["unpinned"] == [PROPOSAL, APPLICATION]
    assert [d["sent"] for d in body["docs"]] == [None, None]
    assert [d["changed"] for d in body["docs"]] == [False, False]

    trio.project.build(PROPOSAL, "v2")
    preview = trio.preview()
    assert [d["change"] for d in preview["docs"]] == ["new", "new"]
    resent = _send_version(trio)
    assert {doc_id: v["round"] for doc_id, v in _pinned(trio).items()} == {PROPOSAL: 2, APPLICATION: 2}
    assert resent["status"] == "active"
    assert [e["changed_docs"] for e in resent["events"] if e["kind"] == "sent"] == [None, None]


async def test__pack__built_from_the_signed_version_after_an_edit(stand: Stand) -> None:
    trio = await _all_approved(stand)
    trio.project.build(PROPOSAL, "v2")

    resp = trio.call(
        trio.author,
        "POST",
        f"{trio.project.base}/submissions",
        json={"profile_id": TOPIC, "items": [], "extra_items": [], "archive_format": "zip"},
    )

    assert resp.status_code == 201, resp.text
    record = resp.json()
    assert [(w["code"], w["doc_id"]) for w in record["warnings"]] == [("changed_after_sent", PROPOSAL)]
    with zipfile.ZipFile(io.BytesIO(Path(record["output_path"]).read_bytes())) as zf:
        texts = [_pdf_text(zf.read(name)) for name in zf.namelist() if name.endswith(".pdf")]
    proposal = [text for text in texts if PROPOSAL in text]
    assert proposal
    assert all("v1" in text and "v2" not in text for text in proposal)
