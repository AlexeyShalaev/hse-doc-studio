"""Сторожа маршрута у входов мимо страницы подписи (docs/design/signing-route.md, разделы 5.5, 6.1 и 6.10).

Правки подписей документа идущего маршрута (409 `route_locked`), «Подписать комплект» для документов маршрута и
маршрут в ответе плана подписей, на настоящем сервере.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.entities import Project, SigningIdentity
from hse_doc_studio.core.enums import DetachedFormat, DetachedOrigin, DetachedVerdict
from hse_doc_studio.core.signing_route.entities import DocSlot
from hse_doc_studio.core.value_objects import DetachedSignature
from hse_doc_studio.use_cases.signatures._studio_signer import StudioSigner
from hse_doc_studio.use_cases.signatures.attach_detached_signature import (
    AttachDetachedSignatureInput,
    AttachDetachedSignatureOutput,
    AttachDetachedSignatureUC,
)
from hse_doc_studio.use_cases.signatures.default_key import DefaultKey, DefaultSigningKey
from hse_doc_studio.use_cases.signatures.sign_submission import DocPreview, SignSubmissionUC, SlotResult
from hse_doc_studio.use_cases.signatures.signing_source import pinned_rel
from hse_doc_studio.use_cases.signing_route import author as author_module

from tests.fakes.signer_profile import make_self_signed
from tests.integration.api.signing_routes.signer_stand import (
    APPLICATION,
    NAMES,
    PNG,
    PROPOSAL,
    FakeKeys,
    Trio,
    install_fake_keys,
    make_trio,
    my,
)
from tests.integration.api.signing_routes.stand import TOPIC, Person, Stand
from tests.integration.api.signing_routes.watch_stand import drain, notifications

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

LOCKED = "Документ на подписании: отмените маршрут, чтобы изменить подписи"
ON_ROUTE = "Документ на подписании по маршруту"


def _code(resp: Any) -> tuple[int, str | None]:
    return resp.status_code, resp.json().get("code") if resp.content else None


def _edits(trio: Trio, who: Person, *, doc_id: str = APPLICATION, slot_id: str = "author") -> dict[str, Any]:
    """Каждая правка подписей, закрытая на время маршрута: размещение, слот, плашка, фиксация, открепленная подпись."""
    base = trio.project.base
    slot = f"{base}/signatures/slots/{slot_id}"
    png = {"file": ("s.png", PNG, "image/png")}
    cert = {"file": ("cert.pem", make_self_signed(NAMES["author"]).cert_pem, "application/x-pem-file")}
    config = {"signing_identity_id": None, "sign_mode": "detached_text", "sign_reason": ""}
    signer = {"owner": NAMES["author"], "cert_id": "1A2B 3C4D"}
    return {
        "placement": lambda: trio.call(
            who, "PATCH", f"{base}/signatures/placements/{doc_id}/{slot_id}", json={"x_mm": 42}
        ),
        "slot config": lambda: trio.call(who, "PATCH", f"{slot}/config", json=config),
        "slot png": lambda: trio.call(who, "POST", f"{slot}/png", files=png),
        "slot png removal": lambda: trio.call(who, "DELETE", f"{slot}/png"),
        "plate signer": lambda: trio.call(who, "PUT", f"{slot}/signer", json=signer),
        "plate signer level": lambda: trio.call(who, "PUT", f"{slot}/signer/level", json={"level": "УКЭП"}),
        "plate signer file": lambda: trio.call(who, "POST", f"{slot}/signer/file", files=cert),
        "plate signer removal": lambda: trio.call(who, "DELETE", f"{slot}/signer"),
        "freeze": lambda: trio.call(who, "POST", f"{base}/docs/{doc_id}/frozen"),
        "unfreeze": lambda: trio.call(who, "DELETE", f"{base}/docs/{doc_id}/frozen"),
        "detached signature removal": lambda: trio.call(who, "DELETE", f"{base}/docs/{doc_id}/detached/{slot_id}"),
        "withheld image shown": lambda: trio.call(who, "DELETE", f"{base}/signatures/withheld/{doc_id}/{slot_id}"),
    }


async def test__active_route__every_signature_edit__409_route_locked_and_nothing_changes(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    before = trio.state()

    answers = {name: edit() for name, edit in _edits(trio, trio.author).items()}
    drain(stand)

    assert {name: _code(resp) for name, resp in answers.items()} == dict.fromkeys(answers, (409, "route_locked"))
    assert {resp.json()["detail"] for resp in answers.values()} == {LOCKED}
    assert trio.state() == before
    route = trio.route()
    assert (route["status"], [e["kind"] for e in route["events"]]) == ("active", ["sent", "approved"])


async def test__cancelled_route__withheld_image_stays__author_shows_it_explicitly(stand: Stand) -> None:
    """Отмена не согласие: картинка научрука остаётся придержанной, пока автор сам не нажмёт «Показать» (5.6)."""
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    held = {APPLICATION: ["supervisor"], PROPOSAL: ["supervisor"]}
    release = f"{trio.project.base}/signatures/withheld/{APPLICATION}/supervisor"
    locked = trio.call(trio.author, "DELETE", release)

    cancelled = trio.call(trio.author, "POST", f"{trio.url}/cancel", json={})
    listed = trio.call(trio.author, "GET", f"{trio.project.base}/signatures").json()["withheld"]
    # Показать может тот, кто правит размещения: рецензенту (подписанту) нельзя.
    by_reviewer = trio.call(trio.supervisor, "DELETE", release)
    shown = trio.call(trio.author, "DELETE", release)
    again = trio.call(trio.author, "DELETE", release)
    drain(stand)

    assert _code(locked) == (409, "route_locked")
    assert cancelled.status_code == 200, cancelled.text
    assert listed == held
    assert by_reviewer.status_code == 403
    assert (shown.status_code, again.status_code) == (204, 204)
    assert trio.withheld() == {PROPOSAL: ["supervisor"]}
    plan = trio.call(trio.author, "GET", f"{trio.project.base}/signature-plan", params={"profile_id": TOPIC}).json()
    reasons = {(d["doc_id"], s["slot_id"]): s["reason"] for d in plan["docs"] for s in d["slots"]}
    assert reasons[(APPLICATION, "supervisor")] != "awaiting_approval"
    assert reasons[(PROPOSAL, "supervisor")] == "awaiting_approval"
    audit = trio.stand.admin().get("/api/admin/audit", params={"target": trio.project.id, "limit": 200}).json()
    released = [e for e in audit["items"] if e["action"] == "signature.release"]
    assert [(e["actor_id"], e["details"]["doc_id"], e["details"]["slot_id"]) for e in released] == [
        (trio.author.id, APPLICATION, "supervisor")
    ]


async def test__active_route__english_interface__message_in_english(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()

    resp = stand.client.post(
        f"{trio.project.base}/docs/{APPLICATION}/frozen", headers={**trio.author.headers, "X-Interface-Language": "en"}
    )

    assert _code(resp) == (409, "route_locked")
    assert resp.json()["detail"] == "The document is out for signing: cancel the signing route to change its signatures"


async def test__active_route__signer_edits_past_their_page__route_locked_too(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()

    # Научрук в свою очередь меняет картинку только на своей странице (`task/image`), общие ручки закрыты и ему.
    png = {"file": ("s.png", PNG, "image/png")}
    past = trio.call(trio.supervisor, "POST", f"{trio.project.base}/signatures/slots/supervisor/png", files=png)
    own = trio.image(trio.supervisor)

    assert _code(past) == (409, "route_locked")
    assert own.status_code == 200, own.text
    assert my(own.json()) == ("to_approve", "approve")


async def test__active_route__slot_outside_the_route_and_its_documents__editable(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    base = trio.project.base
    config = {"signing_identity_id": None, "sign_mode": "detached_text", "sign_reason": ""}

    # Слот академрука в маршрут не входит и на его документах не стоит: его настройка маршрут не задевает.
    free = trio.call(trio.author, "PATCH", f"{base}/signatures/slots/academic_supervisor/config", json=config)
    # А размещение на документе маршрута меняет его видимый слой, чей бы слот ни был.
    on_doc = trio.call(
        trio.author, "PATCH", f"{base}/signatures/placements/{APPLICATION}/academic_supervisor", json={"enabled": True}
    )
    drain(stand)

    assert free.status_code == 200, free.text
    assert _code(on_doc) == (409, "route_locked")
    assert trio.route()["status"] == "active"


async def test__active_route__slot_placed_on_a_route_document__locked(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    base = trio.project.base
    placed = trio.call(
        trio.author, "PATCH", f"{base}/signatures/placements/{APPLICATION}/academic_supervisor", json={"enabled": True}
    )
    assert placed.status_code == 200, placed.text
    trio.sent()

    # Слот не участник маршрута, но стоит на его документе: его картинка это видимый слой документа маршрута.
    png = {"file": ("s.png", PNG, "image/png")}
    resp = trio.call(trio.author, "POST", f"{base}/signatures/slots/academic_supervisor/png", files=png)

    assert _code(resp) == (409, "route_locked")


async def test__route_not_going__signature_edits_allowed_again(stand: Stand, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(author_module, "SEND_INTERVAL", timedelta(0))
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    placement = f"{trio.project.base}/signatures/placements/{APPLICATION}/author"
    trio.sent()
    assert _code(trio.call(trio.author, "PATCH", placement, json={"x_mm": 41})) == (409, "route_locked")

    # Возвращён на доработку: автор правит и отправляет заново.
    assert trio.give_back(trio.supervisor).status_code == 200
    returned = trio.call(trio.author, "PATCH", placement, json={"x_mm": 42})
    trio.sent()
    assert _code(trio.call(trio.author, "PATCH", placement, json={"x_mm": 43})) == (409, "route_locked")

    # Отменён: правки открыты.
    assert trio.call(trio.author, "POST", f"{trio.url}/cancel", json={}).status_code == 200
    cancelled = trio.call(trio.author, "PATCH", placement, json={"x_mm": 44})

    assert (returned.status_code, cancelled.status_code) == (200, 200)
    assert trio.state()["placements"][APPLICATION]["author"]["x_mm"] == 44


async def test__route_stopped_by_calculation__edits_allowed_before_the_stop_is_recorded(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    # Подмена версии на подписи без хука: в хранилище маршрут ещё идёт, по расчёту уже остановлен и правки не держит.
    trio.project.replace_sent(APPLICATION)

    moved = trio.call(
        trio.author, "PATCH", f"{trio.project.base}/signatures/placements/{APPLICATION}/author", json={"x_mm": 42}
    )
    drain(stand)

    assert moved.status_code == 200, moved.text
    # Запись состояния подписей позвала сверку, и она записала остановку по главной причине.
    route = trio.route()
    assert (route["status"], route["stop_reason"]) == ("paused", "sent_changed")


# --- «Подписать комплект» (6.10) ------------------------------------------------------------------------------------


def _bundle(trio: Trio, who: Person, action: str) -> Any:
    body = {"profile_id": TOPIC, "author": None, "identity_id": None, "passphrase": "", "confirm_reset": False}
    return trio.call(who, "POST", f"{trio.project.base}/signature-plan/{action}", json=body)


async def test__sign_bundle__route_documents_not_in_turn__reason_and_route_link__nothing_frozen(
    stand: Stand,
) -> None:
    trio = await make_trio(stand, {"author": "detached"}, plates=("author",), images=("supervisor",), academic="none")
    trio.sent()
    # Автор согласовал до фиксации и ждёт её: научрук ещё меняет видимый слой.
    assert my(trio.task(trio.author)) == ("waiting", "wait")
    before = trio.state()

    preview = _bundle(trio, trio.author, "sign-preview")
    signed = _bundle(trio, trio.author, "sign")

    assert preview.status_code == 200, preview.text
    docs = preview.json()["docs"]
    assert [(d["doc_id"], d["blocker"], d["needs_freeze"], d["route_id"]) for d in docs] == [
        (APPLICATION, ON_ROUTE, False, trio.route_id)
    ]
    assert [(s["slot_id"], s["action"], s["blocker"]) for s in docs[0]["slots"]] == [("author", "none", ON_ROUTE)]
    assert preview.json()["to_sign"] == 0
    assert signed.status_code == 200, signed.text
    assert signed.json()["frozen_docs"] == []
    assert [(r["slot_id"], r["ok"], r["message"]) for r in signed.json()["results"]] == [("author", False, ON_ROUTE)]
    # Комплект документ маршрута не фиксирует и ничего не пишет: маршрут идёт дальше.
    assert trio.state() == before
    assert trio.route()["status"] == "active"


async def test__sign_bundle__participant_in_turn_to_sign__slots_offered_without_freezing(stand: Stand) -> None:
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    trio.sent()
    waiting = _bundle(trio, trio.supervisor, "sign-preview").json()
    assert my(trio.approved(trio.supervisor)) == ("to_sign", "sign")

    turn = _bundle(trio, trio.supervisor, "sign-preview").json()

    # До согласия комплект научрука закрыт; когда маршрут ждёт его подписи, слоты предложены, фиксировать нечего.
    assert {d["blocker"] for d in waiting["docs"]} == {ON_ROUTE}
    assert [(d["doc_id"], d["blocker"], d["needs_freeze"], d["route_id"]) for d in turn["docs"]] == [
        (PROPOSAL, "", False, trio.route_id),
        (APPLICATION, "", False, trio.route_id),
    ]
    assert {s["action"] for d in turn["docs"] for s in d["slots"]} == {"sign"}
    assert {d["token"] for d in turn["docs"]} == {f"pdf:{sha}" for sha in trio.frozen_sha().values()}
    # Чужой комплект: владелец за научрука не подписывает ни в чью очередь.
    owner = _bundle(trio, trio.author, "sign-preview").json()
    assert [s for d in owner["docs"] for s in d["slots"] if s["action"] == "sign"] == []


def _fake_bundle_key(monkeypatch: pytest.MonkeyPatch, keys: FakeKeys) -> None:
    """«Подписать комплект» ключом двойника: настоящую подпись на сервере проверяет раннер, здесь ход маршрута."""

    async def default_key(self: DefaultSigningKey) -> DefaultKey:
        identity = keys.mine()
        return DefaultKey(identity.id if identity else None, identity)

    async def key_allowed(self: StudioSigner) -> None:
        return None

    async def key_signer(self: SignSubmissionUC, identity: SigningIdentity | None) -> Any:
        return keys.plate(identity) if identity is not None else None

    async def sign_doc(
        self: SignSubmissionUC, project: Project, doc: DocPreview, identity: SigningIdentity | None, _passphrase: str
    ) -> list[SlotResult]:
        assert identity is not None
        state = self._signature_repo.get_state(project.folder)
        results: list[SlotResult] = []
        for action in doc.slots:
            if action.action != "sign" or action.blocker:
                results.append(SlotResult(doc.doc_id, action.slot_id, False, action.blocker))
                continue
            pair = DocSlot(doc.doc_id, action.slot_id)
            signature = keys.signature(identity, pair, state.frozen[doc.doc_id].sha256)
            detached = {**state.detached.get(doc.doc_id, {}), action.slot_id: signature}
            state = replace(state, detached={**state.detached, doc.doc_id: detached})
            results.append(SlotResult(doc.doc_id, action.slot_id, True))
        self._signature_repo.save_state(project.folder, state)
        return results

    monkeypatch.setattr(DefaultSigningKey, "get", default_key)
    monkeypatch.setattr(StudioSigner, "require_key_allowed", key_allowed)
    monkeypatch.setattr(SignSubmissionUC, "_key_signer", key_signer)
    monkeypatch.setattr(SignSubmissionUC, "_sign_doc", sign_doc)


async def test__sign_bundle__in_turn_to_sign__route_slots_signed_and_route_completed(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys = install_fake_keys(monkeypatch)
    _fake_bundle_key(monkeypatch, keys)
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    keys.give(trio.supervisor, NAMES["supervisor"])
    trio.sent()
    trio.approved(trio.supervisor)
    frozen = trio.frozen_sha()
    preview = _bundle(trio, trio.supervisor, "sign-preview").json()
    body = {
        "profile_id": TOPIC,
        "author": None,
        "identity_id": None,
        "passphrase": "any",
        "confirm_reset": False,
        "expected": {d["doc_id"]: d["token"] for d in preview["docs"]},
    }

    signed = trio.call(trio.supervisor, "POST", f"{trio.project.base}/signature-plan/sign", json=body)
    drain(stand)

    assert signed.status_code == 200, signed.text
    out = signed.json()
    assert (out["frozen_docs"], [(r["doc_id"], r["ok"]) for r in out["results"]]) == (
        [],
        [(PROPOSAL, True), (APPLICATION, True)],
    )
    # Комплект подписал поверх фиксации маршрута и маршрут пересчитан: подписи в истории, маршрут завершён.
    assert trio.frozen_sha() == frozen
    assert trio.signed_pdf_sha() == {doc: {"supervisor": sha} for doc, sha in frozen.items()}
    route = trio.route()
    assert route["status"] == "completed"
    assert [e["kind"] for e in route["events"]] == [
        "sent",
        "approved",
        "frozen",
        "approved",
        "signed",
        "signed",
        "completed",
    ]
    assert {e["who"] for e in route["events"] if e["kind"] == "signed"} == {NAMES["supervisor"]}
    assert out["plan"]["route"]["status"] == "completed"
    assert len(notifications(stand, trio, "author", "signing_completed")) == 1


def _fake_attach(verdict: DetachedVerdict) -> Any:
    """Двойник загрузки готовой подписи: запись открепленной подписи над текущей фиксацией с нужным вердиктом."""

    async def execute(
        self: AttachDetachedSignatureUC, inp: AttachDetachedSignatureInput
    ) -> AttachDetachedSignatureOutput:
        folder = settings.data_dir / "projects" / str(inp.project_id)
        state = self._signature_repo.get_state(folder)
        signature = DetachedSignature(
            file=f".hse-studio/detached/{inp.doc_id}/{inp.slot_id}.asc",
            format=DetachedFormat.openpgp,
            origin=DetachedOrigin.uploaded,
            pdf_sha256=state.frozen[inp.doc_id].sha256,
            verdict=verdict,
            signer=NAMES["supervisor"],
            signer_id="ABCDEF",
            added_at=datetime.now(UTC).isoformat(),
        )
        detached = {**state.detached.get(inp.doc_id, {}), inp.slot_id: signature}
        self._signature_repo.save_state(folder, replace(state, detached={**state.detached, inp.doc_id: detached}))
        return AttachDetachedSignatureOutput(signature=signature)

    return execute


async def test__ready_signature__uploaded_twice__one_signed_event(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(AttachDetachedSignatureUC, "execute", _fake_attach(DetachedVerdict.valid))
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    trio.sent()
    trio.approved(trio.supervisor)
    upload = f"{trio.project.base}/docs/{PROPOSAL}/detached/supervisor"
    file = {"file": ("signature.asc", b"-----BEGIN PGP SIGNATURE-----", "application/pgp-signature")}

    first = trio.call(trio.supervisor, "POST", upload, files=file)
    # Подписант заменил файл подписи той же заявки, пока маршрут ждёт его подпись на заявлении.
    second = trio.call(trio.supervisor, "POST", upload, files=file)
    drain(stand)

    assert (first.status_code, second.status_code) == (200, 200)
    assert trio.events() == ["sent", "approved", "frozen", "approved", "signed"]
    assert trio.route()["status"] == "active"


async def test__completed_route__detached_signature_removed__route_waits_for_that_slot_again(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(AttachDetachedSignatureUC, "execute", _fake_attach(DetachedVerdict.valid))
    trio = await make_trio(stand, {"supervisor": "detached"}, plates=("supervisor",), academic="none")
    trio.sent()
    trio.approved(trio.supervisor)
    file = {"file": ("signature.asc", b"-----BEGIN PGP SIGNATURE-----", "application/pgp-signature")}
    removal = f"{trio.project.base}/docs/{PROPOSAL}/detached/supervisor"
    for doc_id in (PROPOSAL, APPLICATION):
        trio.call(trio.supervisor, "POST", f"{trio.project.base}/docs/{doc_id}/detached/supervisor", files=file)
    assert trio.route()["status"] == "completed"

    # Завершённый маршрут удаление подписи не запрещает: слот снова ждёт подписи, маршрут не останавливается (5.5).
    removed = trio.call(trio.supervisor, "DELETE", removal)
    drain(stand)

    assert removed.status_code == 204, removed.text
    route = trio.route()
    assert (route["status"], route["phase"], route["stop_reason"]) == ("active", "signing", None)
    assert my(trio.task(trio.supervisor)) == ("to_sign", "sign")
    # Пока маршрут снова идёт, удалить вторую подпись мимо маршрута уже нельзя.
    locked = trio.call(trio.supervisor, "DELETE", f"{trio.project.base}/docs/{APPLICATION}/detached/supervisor")
    assert _code(locked) == (409, "route_locked")


# --- маршрут в плане подписей (6.1) ---------------------------------------------------------------------------------


def _plan(trio: Trio, who: Person, **params: str) -> dict[str, Any]:
    resp = trio.call(who, "GET", f"{trio.project.base}/signature-plan", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _route_states(plan: dict[str, Any]) -> dict[tuple[str, str], str | None]:
    return {(d["doc_id"], s["slot_id"]): s["route_state"] for d in plan["docs"] for s in d["slots"]}


async def test__plan__route_of_the_checkpoint_and_of_the_document__with_participant_states(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    draft = _plan(trio, trio.author, profile_id=TOPIC)
    trio.sent()

    by_point = _plan(trio, trio.author, profile_id=TOPIC)
    by_doc = _plan(trio, trio.supervisor, doc_id=PROPOSAL)
    whole = _plan(trio, trio.author)

    # Черновик документы не держит: в плане маршрута ещё нет.
    assert (draft["route"], set(_route_states(draft).values())) == (None, {None})
    expected = {
        "id": trio.route_id,
        "profile_id": TOPIC,
        "status": "active",
        "phase": "approval",
        "round": 1,
        "current_step": 2,
        "steps_total": 2,
        "stop_reason": None,
    }
    assert by_point["route"] == expected
    assert by_doc["route"] == expected
    assert _route_states(by_point) == {
        (PROPOSAL, "supervisor"): "to_approve",
        (APPLICATION, "author"): "done",
        (APPLICATION, "supervisor"): "to_approve",
    }
    # План всего проекта не про одну точку: маршрута в ответе нет, состояния слотов есть.
    assert whole["route"] is None
    assert _route_states(whole)[(APPLICATION, "supervisor")] == "to_approve"


async def test__plan__state_is_calculated__stop_and_completion_visible_before_they_are_recorded(
    stand: Stand,
) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    # Подмена версии на подписи без хука: маршрут в хранилище идёт, план показывает вычисленную остановку.
    trio.project.replace_sent(PROPOSAL)

    stopped = _plan(trio, trio.author, profile_id=TOPIC)["route"]

    assert (stopped["status"], stopped["stop_reason"], stopped["phase"], stopped["current_step"]) == (
        "paused",
        "sent_changed",
        None,
        None,
    )


async def test__plan__completed_route__kept_until_archived(stand: Stand) -> None:
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    trio.approved(trio.supervisor)

    done = _plan(trio, trio.author, profile_id=TOPIC)
    assert trio.call(trio.author, "POST", f"{trio.url}/archive", json={}).status_code == 200
    archived = _plan(trio, trio.author, profile_id=TOPIC)

    assert (done["route"]["status"], done["route"]["phase"], done["route"]["current_step"]) == (
        "completed",
        "done",
        None,
    )
    assert set(_route_states(done).values()) == {"done"}
    assert (archived["route"], set(_route_states(archived).values())) == (None, {None})


async def test__plan__early_approver_waits_for_the_freeze__not_counted_until_their_turn(stand: Stand) -> None:
    trio = await make_trio(stand, {"author": "detached"}, plates=("author",), images=("supervisor",), academic="none")
    trio.sent()
    # Автор согласовал до фиксации: его ЭП маршрут попросит после согласия научрука, сейчас звать его нечего.
    assert my(trio.task(trio.author)) == ("waiting", "wait")

    waiting = _plan(trio, trio.author, profile_id=TOPIC)
    whole = _plan(trio, trio.author)
    trio.approved(trio.supervisor)
    turn = _plan(trio, trio.author, profile_id=TOPIC)

    mine = {(d["doc_id"], s["slot_id"]): d["held_by_route"] for d in whole["docs"] for s in d["slots"] if s["is_mine"]}
    # Во всём проекте ждёт только слот документа вне маршрута (отчёт): его можно подписать сейчас.
    assert mine == {(APPLICATION, "author"): True, ("report", "author"): False}
    assert (waiting["waiting_for_me"], whole["waiting_for_me"]) == (0, 1)
    assert my(trio.task(trio.author)) == ("to_sign", "sign")
    assert turn["waiting_for_me"] == 1


async def test__route__card_name_and_who_still_changes_the_visible_layer(stand: Stand) -> None:
    trio = await make_trio(stand, {"author": "detached"}, plates=("author",), images=("supervisor",), academic="none")
    trio.sent()

    people = {p["persona"]: p for step in trio.route()["steps"] for p in step}
    task = {p["persona"]: p for step in trio.task(trio.author)["steps"] for p in step}

    assert {k: (p["card_name"], p["changes_visible"]) for k, p in people.items()} == {
        "author": (NAMES["author"], False),
        "supervisor": (NAMES["supervisor"], True),
    }
    assert {k: (p["card_name"], p["changes_visible"]) for k, p in task.items()} == {
        "author": (NAMES["author"], False),
        "supervisor": (NAMES["supervisor"], True),
    }


async def test__sign_the_current_build__held_by_a_route__409_then_after_archive__unpinned(stand: Stand) -> None:
    """«Подписывать текущую сборку» (12.4): пока маршрут держит документ, нельзя; снятый с контроля не держит, а его
    версия на подписи остаётся, пока её не снимут."""
    trio = await make_trio(stand, images=("author", "supervisor"), academic="none")
    trio.sent()
    trio.approved(trio.supervisor)
    sha = trio.state()["pinned"][APPLICATION]["sha256"]
    unpin = f"{trio.project.base}/docs/{APPLICATION}/pinned"

    locked = trio.call(trio.author, "DELETE", unpin)
    archived = trio.call(trio.author, "POST", f"{trio.url}/archive", json={})
    kept = trio.state()["pinned"]
    by_reviewer = trio.call(trio.supervisor, "DELETE", unpin)
    unpinned = trio.call(trio.author, "DELETE", unpin)
    drain(stand)

    assert _code(locked) == (409, "route_locked")
    assert archived.status_code == 200, archived.text
    assert set(kept) == {APPLICATION, PROPOSAL}
    assert by_reviewer.status_code == 403
    assert unpinned.status_code == 204, unpinned.text
    assert set(trio.state()["pinned"]) == {PROPOSAL}
    assert not (trio.project.folder / pinned_rel(APPLICATION)).exists()
    resp = stand.admin().get(
        "/api/admin/audit", params={"target": trio.project.id, "action": "signature.unpin", "limit": 10}
    )
    assert resp.status_code == 200, resp.text
    [entry] = resp.json()["items"]
    assert (entry["details"]["doc_id"], entry["details"]["sha256"]) == (APPLICATION, sha)
