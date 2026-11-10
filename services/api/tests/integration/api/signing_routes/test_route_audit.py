"""Журнал аудита маршрута подписания (docs/design/signing-route.md, раздел 6.7) на настоящем сервере.

Записи `signing_route.*` читаются так, как их видит админ: `/api/admin/audit` с фильтром по объекту (проекту).
Проверяется, кто и что записал по ходу маршрута, что подписи маршрута несут `route_id`, и что в журнал не
попадают комментарий возврата, сообщение автора, содержимое картинки и пароль ключа.
"""

from __future__ import annotations

from typing import Any

import pytest
from hse_doc_studio.core.enums import DetachedVerdict
from hse_doc_studio.core.identity.redaction import REDACTED
from hse_doc_studio.use_cases.signatures.attach_detached_signature import (
    AttachDetachedSignatureInput,
    AttachDetachedSignatureOutput,
    AttachDetachedSignatureUC,
)
from hse_doc_studio.use_cases.signing_route.key_signer import RouteKeySigner

from tests.fakes.signer_profile import make_png, make_self_signed
from tests.integration.api.signing_routes.signer_stand import (
    APPLICATION,
    PASSPHRASE,
    PROPOSAL,
    FakeKeys,
    Trio,
    install_fake_keys,
    make_trio,
    my,
)
from tests.integration.api.signing_routes.stand import Person, Stand
from tests.integration.api.signing_routes.test_signer_task_api import _fake_attach, _upload

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

KEY = {"identity_id": None, "passphrase": PASSPHRASE}
COMMENT = "Уточните цель проекта в разделе 2"
MESSAGE = "Прошу подписать заявление до пятницы."


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> FakeKeys:
    """Ключи людей; подпись двойника пишет в аудит `signature.sign`, как настоящая подпись ключом Студии."""
    installed = install_fake_keys(monkeypatch)
    fake_sign = RouteKeySigner.sign

    async def sign(self: RouteKeySigner, point: Any, pairs: Any, identity: Any, passphrase: str) -> Any:
        signed = await fake_sign(self, point, pairs, identity, passphrase)
        for pair in signed:
            await self._signer.audit.record(
                "signature.sign", project_id=point.project_id, details={"doc_id": pair.doc_id, "slot_id": pair.slot_id}
            )
        return signed

    monkeypatch.setattr(RouteKeySigner, "sign", sign)
    return installed


def _audit(trio: Trio, *categories: str) -> list[dict[str, Any]]:
    """Записи журнала о проекте, старые первыми, как их отдаёт админке `/api/admin/audit`."""
    params: dict[str, Any] = {"target": trio.project.id, "limit": 200}
    if categories:
        params["category"] = list(categories)
    resp = trio.stand.admin().get("/api/admin/audit", params=params)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["next_cursor"] is None
    return list(reversed(body["items"]))


def _route_audit(trio: Trio) -> list[dict[str, Any]]:
    return _audit(trio, "signing_route")


def _actions(events: list[dict[str, Any]]) -> list[str]:
    return [e["action"] for e in events]


def _who(events: list[dict[str, Any]]) -> list[tuple[str, str | None]]:
    return [(e["action"].removeprefix("signing_route."), e["actor_id"]) for e in events]


def _participants(trio: Trio) -> dict[str, str]:
    return {p["persona"]: p["id"] for step in trio.route()["steps"] for p in step}


def _one(events: list[dict[str, Any]], action: str) -> dict[str, Any]:
    [found] = [e for e in events if e["action"] == action]
    return found


async def test__images_route__draft_edit_send_return_resend_cancel__every_step_in_the_audit_log(stand: Stand) -> None:
    trio = await make_trio(stand)
    author, supervisor, academic = trio.author, trio.supervisor, trio.academic
    ids = _participants(trio)
    png = make_png(200, 50)

    trio.sent()
    assert trio.image(supervisor, png).status_code == 200
    trio.approved(supervisor)
    assert trio.image(academic).status_code == 200
    assert trio.give_back(academic, COMMENT).status_code == 200
    # Раньше чем через минуту маршрут повторно не отправить: отказ в журнал не попадает.
    assert trio.send().status_code == 429
    assert trio.call(author, "POST", f"{trio.url}/cancel", json={}).status_code == 200

    events = _route_audit(trio)
    assert _who(events) == [
        ("create", author.id),
        ("update", author.id),
        ("send", author.id),
        ("approve", author.id),
        ("signer_image", supervisor.id),
        ("approve", supervisor.id),
        ("signer_image", academic.id),
        ("return", academic.id),
        ("cancel", author.id),
    ]
    # Все записи о проекте: админ находит их фильтром «все события этого объекта».
    assert {e["target"] for e in events} == {trio.project.id}
    assert {e["details"]["project_id"] for e in events} == {trio.project.id}
    assert {e["details"]["route_id"] for e in events} == {trio.route_id}
    assert {e["details"]["profile_id"] for e in events} == {"topic-approval"}
    assert [e["details"]["round"] for e in events] == [0, 0, 1, 1, 1, 1, 1, 1, 1]
    assert events[0]["actor"]["name"] == "Иванов Иван Иванович"

    created, updated, sent = (e["details"] for e in events[:3])
    assert (created["docs"], created["steps"]) == ([PROPOSAL, APPLICATION], 2)
    assert (updated["steps"], updated["participants"], updated["has_message"]) == (3, 3, True)
    assert updated["extra_slots"] == [{"doc_id": APPLICATION, "slot_id": "academic_supervisor"}]
    assert (sent["docs"], sent["steps"], sent["participants"]) == ([PROPOSAL, APPLICATION], 3, 3)
    assert (sent["resend"], sent["deadline"]) == (False, None)

    own, approved = events[3]["details"], events[5]["details"]
    assert (own["participant_id"], own["persona"], own["step"]) == (ids["author"], "author", 1)
    assert own["slots"] == [{"doc_id": APPLICATION, "slot_id": "author"}]
    assert (approved["participant_id"], approved["step"], approved["user_id"]) == (ids["supervisor"], 2, supervisor.id)
    assert approved["slots"] == [
        {"doc_id": PROPOSAL, "slot_id": "supervisor"},
        {"doc_id": APPLICATION, "slot_id": "supervisor"},
    ]

    image = events[4]["details"]
    assert (image["slot_ids"], image["size"], image["remember"]) == (["supervisor"], len(png), False)
    assert len(image["sha256"]) == 64

    returned = events[7]["details"]
    assert (returned["participant_id"], returned["step"], returned["reason"]) == (
        ids["academic_supervisor"],
        3,
        "returned",
    )
    # Комментарий возврата и сообщение автора остаются в маршруте, в журнал аудита не попадают.
    dumped = str(events)
    assert COMMENT not in dumped
    assert MESSAGE not in dumped
    assert REDACTED not in dumped
    assert [e["comment"] for e in trio.route()["events"] if e["kind"] == "returned"] == [COMMENT]


async def test__plate_from_the_studio_key__freeze_and_signatures_carry_the_route_id(
    stand: Stand, keys: FakeKeys
) -> None:
    trio = await make_trio(stand, {"supervisor": "detached"}, academic="none")
    author, supervisor = trio.author, trio.supervisor
    key = keys.give(supervisor, "Петров Пётр Петрович")
    ids = _participants(trio)
    trio.sent()

    # Плашка научрука последняя правка видимого слоя: документы фиксирует маршрут от имени научрука.
    assert trio.plate_key(supervisor, str(key.id)).status_code == 200
    done = trio.approved(supervisor, sign=KEY)
    assert done["route"]["status"] == "completed"
    assert trio.call(author, "POST", f"{trio.url}/archive", json={}).status_code == 200

    events = _audit(trio, "signing_route", "signature")
    tail = events[_actions(events).index("signing_route.send") :]
    assert [(e["action"], e["actor_id"]) for e in tail] == [
        ("signing_route.send", author.id),
        ("signing_route.approve", author.id),
        ("signing_route.signer_plate", supervisor.id),
        ("signature.freeze", supervisor.id),
        ("signature.freeze", supervisor.id),
        ("signature.sign", supervisor.id),
        ("signature.sign", supervisor.id),
        ("signing_route.approve", supervisor.id),
        ("signing_route.sign", supervisor.id),
        ("signing_route.sign", supervisor.id),
        ("signing_route.complete", None),
        ("signing_route.archive", author.id),
    ]
    # Фиксация и подписи, сделанные в маршруте, помечены им.
    marked = [e for e in tail if e["action"].startswith("signature.")]
    assert {e["details"]["route_id"] for e in marked} == {trio.route_id}
    assert sorted(e["details"]["doc_id"] for e in marked[:2]) == sorted([PROPOSAL, APPLICATION])

    plate = _one(tail, "signing_route.signer_plate")["details"]
    assert plate == {
        "project_id": trio.project.id,
        "route_id": trio.route_id,
        "profile_id": "topic-approval",
        "round": 1,
        "participant_id": ids["supervisor"],
        "persona": "supervisor",
        "step": 2,
        "user_id": supervisor.id,
        "slot_ids": ["supervisor"],
        "source": "studio",
        "plate_kind": "openpgp",
        "cert_id": supervisor.id.upper()[:16],
    }
    signed = [e["details"] for e in tail if e["action"] == "signing_route.sign"]
    assert [(d["doc_id"], d["slot_id"], d["step"]) for d in signed] == [
        (PROPOSAL, "supervisor", 2),
        (APPLICATION, "supervisor", 2),
    ]
    assert _one(tail, "signing_route.complete")["details"]["docs"] == [PROPOSAL, APPLICATION]
    # Пароль ключа в журнале не появляется ни под каким именем.
    assert PASSPHRASE not in str(events)
    assert REDACTED not in str(events)


async def test__method_and_plate_changed_by_the_approval__both_in_the_audit_log(stand: Stand, keys: FakeKeys) -> None:
    trio = await make_trio(stand, academic="none")
    supervisor = trio.supervisor
    keys.give(supervisor, "Петров Пётр Петрович")
    trio.sent()

    refused = trio.approve(supervisor, method="pades")
    done = trio.approved(supervisor, method="detached", sign=KEY)

    assert refused.status_code == 409
    assert done["route"]["status"] == "completed"
    events = _route_audit(trio)
    assert _actions(events)[3:] == [
        "signing_route.signer_method",
        "signing_route.signer_plate",
        "signing_route.approve",
        "signing_route.sign",
        "signing_route.sign",
        "signing_route.complete",
    ]
    method = _one(events, "signing_route.signer_method")
    assert (method["actor_id"], method["details"]["method"], method["details"]["slot_ids"]) == (
        supervisor.id,
        "detached",
        ["supervisor"],
    )
    plate = _one(events, "signing_route.signer_plate")["details"]
    assert (plate["source"], plate["plate_kind"]) == ("approval", "openpgp")


async def test__plate_from_a_certificate_file__metadata_only(stand: Stand) -> None:
    trio = await make_trio(stand, {"supervisor": "detached"}, academic="none")
    trio.sent()
    cert = make_self_signed("Петров Пётр Петрович", serial=0x1A2B)

    rejected = trio.plate_file(trio.supervisor, cert.key_pem + cert.cert_pem)
    accepted = trio.plate_file(trio.supervisor, cert.cert_pem)

    assert rejected.status_code == 400
    assert accepted.status_code == 200, accepted.text
    events = _route_audit(trio)
    plate = _one(events, "signing_route.signer_plate")["details"]
    assert (plate["source"], plate["plate_kind"], plate["slot_ids"]) == ("file", "x509", ["supervisor"])
    assert plate["cert_id"] == trio.state()["slots"]["supervisor"]["signer"]["cert_id"]
    # Ни сертификата, ни закрытого ключа из отвергнутого файла в журнале нет.
    dumped = str(_audit(trio))
    assert "BEGIN" not in dumped
    assert REDACTED not in dumped


async def test__image_remembered_in_the_profile__profile_record_carries_the_route_id(stand: Stand) -> None:
    trio = await make_trio(stand, academic="none")
    trio.sent()

    assert trio.image(trio.supervisor, remember=True).status_code == 200

    resp = stand.admin().get("/api/admin/audit", params={"action": "signature.profile_image", "limit": 50})
    mine = [e for e in resp.json()["items"] if e["actor_id"] == trio.supervisor.id]
    assert [e["details"]["route_id"] for e in mine] == [trio.route_id]
    assert _one(_route_audit(trio), "signing_route.signer_image")["details"]["remember"] is True


def _attach_with_audit(verdict: DetachedVerdict) -> Any:
    """Двойник загрузки готовой подписи, который пишет в аудит `signature.attach`, как настоящий сценарий."""
    fake = _fake_attach(verdict)

    async def execute(
        self: AttachDetachedSignatureUC, inp: AttachDetachedSignatureInput
    ) -> AttachDetachedSignatureOutput:
        out = await fake(self, inp)
        assert self._audit is not None
        await self._audit.record(
            "signature.attach", project_id=inp.project_id, details={"doc_id": inp.doc_id, "slot_id": inp.slot_id}
        )
        return out

    return execute


async def test__ready_signature_in_turn__attach_carries_the_route_id_and_the_route_records_the_signature(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(AttachDetachedSignatureUC, "execute", _attach_with_audit(DetachedVerdict.valid))
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    supervisor = trio.supervisor
    trio.sent()
    assert my(trio.approved(supervisor)) == ("to_sign", "sign")

    assert _upload(trio, supervisor, PROPOSAL).status_code == 200
    assert _upload(trio, supervisor, APPLICATION).status_code == 200

    events = _audit(trio, "signing_route", "signature")
    # Плашка научрука известна заранее: документы фиксирует отправка, от имени автора.
    tail = events[_actions(events).index("signature.freeze") :]
    assert [(e["action"], e["actor_id"]) for e in tail] == [
        ("signature.freeze", trio.author.id),
        ("signature.freeze", trio.author.id),
        ("signing_route.send", trio.author.id),
        ("signing_route.approve", trio.author.id),
        ("signing_route.approve", supervisor.id),
        ("signature.attach", supervisor.id),
        ("signing_route.sign", supervisor.id),
        ("signature.attach", supervisor.id),
        ("signing_route.sign", supervisor.id),
        ("signing_route.complete", None),
    ]
    assert {e["details"]["route_id"] for e in tail} == {trio.route_id}


async def test__signature_outside_a_route__no_route_id(stand: Stand, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AttachDetachedSignatureUC, "execute", _attach_with_audit(DetachedVerdict.valid))
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    author = trio.author
    # Маршрут только черновик: документ не под маршрутом, владелец фиксирует и прикладывает подпись сам.
    assert trio.call(author, "POST", f"{trio.project.base}/docs/{PROPOSAL}/frozen").status_code == 200

    assert _upload(trio, author, PROPOSAL).status_code == 200

    events = [e for e in _audit(trio, "signature") if e["action"] in {"signature.freeze", "signature.attach"}]
    assert _actions(events) == ["signature.freeze", "signature.attach"]
    assert all("route_id" not in e["details"] for e in events)


async def test__reminder__manual_reminder_in_the_audit_log(stand: Stand) -> None:
    trio = await make_trio(stand, academic="none")
    trio.sent()
    supervisor_id = _participants(trio)["supervisor"]

    reminded = trio.call(trio.author, "POST", f"{trio.url}/participants/{supervisor_id}/remind", json={})

    assert reminded.status_code == 200, reminded.text
    remind = _one(_route_audit(trio), "signing_route.remind")
    assert remind["actor_id"] == trio.author.id
    details = remind["details"]
    assert (details["participant_id"], details["user_id"], details["step"]) == (supervisor_id, trio.supervisor.id, 2)
    assert (details["trigger"], details["delivery"]) == ("manual", reminded.json()["delivery"])


async def test__document_rebuilt__pause_recorded_by_the_server(stand: Stand) -> None:
    trio = await make_trio(stand, academic="none")
    trio.sent()
    trio.project.build(PROPOSAL, "v2")

    refused = trio.approve(trio.supervisor, expected={})

    assert refused.status_code == 409
    pause = _one(_route_audit(trio), "signing_route.pause")
    assert (pause["actor_id"], pause["actor"], pause["details"]["reason"]) == (None, None, "rebuilt")


async def test__new_draft_of_the_point__previous_cancelled_route_archived_with_a_reference(stand: Stand) -> None:
    trio = await make_trio(stand, academic="none")
    author: Person = trio.author
    assert trio.call(author, "POST", f"{trio.url}/cancel", json={}).status_code == 200

    again = trio.call(author, "POST", trio.project.routes, json={"profile_id": "topic-approval"})

    assert again.status_code == 201, again.text
    new_id = again.json()["id"]
    events = _route_audit(trio)
    assert _who(events) == [
        ("create", author.id),
        ("cancel", author.id),
        ("archive", author.id),
        ("create", author.id),
    ]
    archived, created = events[2]["details"], events[3]["details"]
    assert (archived["route_id"], archived["superseded_by"]) == (trio.route_id, new_id)
    assert created["route_id"] == new_id
