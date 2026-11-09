"""«Отправить и подписать» (docs/design/signing-route.md, разделы 4.4 и 8): L = 0, отправка фиксирует и подписывает.

Точка «Защита КП»: отчёт с подписью автора открепленной ЭП и плашкой, данные плашки известны. Никто не меняет
видимый слой, поэтому отправка сразу фиксирует отчёт, а «Отправить и подписать» в том же запросе подписывает слот
автора. Подпись ключом Студии заменена двойником (настоящую подпись на сервере проверяет раннер): здесь проверяется
сценарий маршрута, а не криптография, которую покрывают тесты «Подписать комплект».
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import DetachedFormat, DetachedOrigin, DetachedVerdict, SigningIdentityKind
from hse_doc_studio.core.signing_route.entities import DocSlot
from hse_doc_studio.core.value_objects import DetachedSignature
from hse_doc_studio.use_cases.signatures._studio_signer import KeyPassphraseRequiredError
from hse_doc_studio.use_cases.signing_route.key_signer import KeyRequest, RouteKeySigner
from hse_doc_studio.use_cases.signing_route.point import RoutePoint

from tests.integration.api.signing_routes.stand import Person, Project, Stand, make_project, person

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

FINAL = "final"
PLATE = {
    "kind": "openpgp",
    "owner": "Иванов Иван Иванович",
    "cert_id": "1A2B 3C4D",
    "valid_from": None,
    "valid_to": None,
    "signer_id": "ABCDEF0123456789",
    "level": "",
}
IDENTITY = SigningIdentity(
    id=uuid4(),
    label="Мой ключ",
    kind=SigningIdentityKind.openpgp,
    subject_cn="Иванов Иван Иванович",
    not_after=datetime(2030, 1, 1, tzinfo=UTC),
    trusted=False,
    created_at=datetime(2026, 1, 1, tzinfo=UTC),
    fingerprint="ABCDEF0123456789",
)


async def _check(self: RouteKeySigner, request: KeyRequest) -> SigningIdentity:
    if request.passphrase != "correct horse":
        raise KeyPassphraseRequiredError
    return IDENTITY


async def _sign(
    self: RouteKeySigner, point: RoutePoint, pairs: Any, identity: SigningIdentity, passphrase: str
) -> tuple[DocSlot, ...]:
    """Двойник подписи ключом: файл подписи над текущей фиксацией с вердиктом «действительна»."""
    folder = point.project.folder
    state = self._signatures.get_state(folder)
    for pair in pairs:
        frozen = state.frozen[pair.doc_id]
        signature = DetachedSignature(
            file=f".hse-studio/detached/{pair.doc_id}/{pair.slot_id}.asc",
            format=DetachedFormat.openpgp,
            origin=DetachedOrigin.studio,
            pdf_sha256=frozen.sha256,
            verdict=DetachedVerdict.valid,
            signer=identity.subject_cn,
            signer_id=identity.fingerprint or "",
            added_at=datetime.now(UTC).isoformat(),
        )
        detached = {**state.detached.get(pair.doc_id, {}), pair.slot_id: signature}
        state = replace(state, detached={**state.detached, pair.doc_id: detached})
    self._signatures.save_state(folder, state)
    return tuple(pairs)


async def _broken_sign(self: RouteKeySigner, *_args: Any) -> tuple[DocSlot, ...]:
    raise ValueError("gpg отказал в подписи: Bad passphrase")


@pytest.fixture
def fake_key(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setattr(RouteKeySigner, "check", _check)
    monkeypatch.setattr(RouteKeySigner, "sign", _sign)
    return monkeypatch


async def _route(stand: Stand) -> tuple[Project, Person, dict[str, Any]]:
    author = await person(stand, "Иванов Иван Иванович")
    project = make_project(stand, author)
    project.build("report")
    path = project.folder / ".hse-studio" / "signatures.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"slots": {}, "placements": {}}
    state["slots"]["author"] = {
        "png_path": None,
        "natural_width_px": None,
        "natural_height_px": None,
        "signing_identity_id": None,
        "sign_mode": "detached_text",
        "sign_reason": "",
        "signer": PLATE,
    }
    # Без включённого размещения слот с плашкой не бывает подписан (placement_off), маршрут не завершился бы.
    state["placements"]["report"] = {
        "author": {"enabled": True, "page": 1, "x_mm": 120.0, "y_mm": 230.0, "width_mm": 60.0, "sign_date": None}
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    created = project.call(author, "POST", project.routes, json={"profile_id": FINAL})
    assert created.status_code == 201, created.text
    return project, author, created.json()


def _send(project: Project, author: Person, route: dict[str, Any], sign: dict[str, Any] | None) -> Any:
    preview = project.call(author, "POST", f"{project.routes}/{route['id']}/preview", json={}).json()
    expected = {d["doc_id"]: d["token"] for d in preview["docs"]}
    return project.call(
        author, "POST", f"{project.routes}/{route['id']}/send", json={"expected": expected, "sign": sign}
    )


def _state(project: Project) -> dict[str, Any]:
    return json.loads((project.folder / ".hse-studio" / "signatures.json").read_text(encoding="utf-8"))


async def test__preview__nobody_changes_visible_layer__send_and_sign_offered(stand: Stand) -> None:
    project, author, route = await _route(stand)

    preview = project.call(author, "POST", f"{project.routes}/{route['id']}/preview", json={}).json()

    assert preview["blockers"] == []
    assert (preview["can_send"], preview["can_send_and_sign"], preview["visual_step"]) == (True, True, 0)
    assert [(p["persona"], p["method"], p["plate_ready"], p["actions"]) for p in preview["participants"]] == [
        ("author", "detached", True, 1)
    ]


async def test__send__plain__freezes_at_once_and_asks_sender_to_sign(stand: Stand) -> None:
    project, author, route = await _route(stand)

    resp = _send(project, author, route, None)

    assert resp.status_code == 200, resp.text
    sent = resp.json()
    assert (sent["status"], sent["phase"], sent["current_step"]) == ("active", "signing", None)
    me = sent["steps"][0][0]
    assert (me["state"], me["next_action"]) == ("to_sign", "sign")
    assert me["notified_at"] is not None
    assert [e["kind"] for e in sent["events"]] == ["sent", "approved", "frozen"]
    assert sent["events"][2]["who"] is None
    assert [d["frozen"] for d in sent["docs"]] == [True]
    assert "report" in _state(project)["frozen"]


async def test__send_and_sign__freezes_signs_and_completes(stand: Stand, fake_key: pytest.MonkeyPatch) -> None:
    project, author, route = await _route(stand)

    resp = _send(project, author, route, {"identity_id": None, "passphrase": "correct horse"})

    assert resp.status_code == 200, resp.text
    done = resp.json()
    assert (done["status"], done["phase"]) == ("completed", "done")
    assert done["completed_at"] == done["sent_at"]
    assert [(p["state"], p["next_action"]) for step in done["steps"] for p in step] == [("done", "done")]
    assert [e["kind"] for e in done["events"]] == ["sent", "approved", "frozen", "signed", "completed"]
    assert [s["status"] for d in done["docs"] for s in d["slots"]] == ["signed"]
    state = _state(project)
    assert state["detached"]["report"]["author"]["pdf_sha256"] == state["frozen"]["report"]["sha256"]


async def test__send_and_sign__passphrase_missing__nothing_sent(stand: Stand, fake_key: pytest.MonkeyPatch) -> None:
    project, author, route = await _route(stand)

    resp = _send(project, author, route, {"identity_id": None, "passphrase": None})

    assert resp.status_code == 400
    assert resp.json()["code"] == "passphrase_required"
    after = project.call(author, "GET", f"{project.routes}/{route['id']}").json()
    assert after["status"] == "draft"
    assert "report" not in _state(project).get("frozen", {})


async def test__send_and_sign__signing_fails__route_is_sent_and_waits_for_signature(
    stand: Stand, fake_key: pytest.MonkeyPatch
) -> None:
    fake_key.setattr(RouteKeySigner, "sign", _broken_sign)
    project, author, route = await _route(stand)

    resp = _send(project, author, route, {"identity_id": None, "passphrase": "correct horse"})

    assert resp.status_code == 400
    assert resp.json()["code"] == "sign_failed"
    assert "Bad passphrase" in resp.json()["detail"]
    after = project.call(author, "GET", f"{project.routes}/{route['id']}").json()
    assert (after["status"], after["phase"]) == ("active", "signing")
    assert [(p["state"], p["next_action"]) for step in after["steps"] for p in step] == [("to_sign", "sign")]


async def test__send_and_sign__server_keys_forbidden__403_and_nothing_sent(stand: Stand) -> None:
    project, author, route = await _route(stand)

    resp = _send(project, author, route, {"identity_id": str(UUID(int=7)), "passphrase": None})

    # На установке закрытые ключи на сервере запрещены (по умолчанию): ключ даже не ищется.
    assert resp.status_code == 403
    assert resp.json()["code"] == "server_keys_forbidden"
    assert project.call(author, "GET", f"{project.routes}/{route['id']}").json()["status"] == "draft"
