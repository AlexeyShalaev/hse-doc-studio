"""Стенд сценариев подписанта: маршрут «автор, научрук, академрук» точки «Заявка на тему КП» на настоящем сервере.

Автор владелец проекта, научрук и академрук рецензенты с персонами. У научрука слоты на заявке и заявлении, у
автора и академрука (необязательный слот, включён автором) на заявлении. Способ каждого задаётся до отправки.

Подпись ключом Студии заменена двойником, как в тестах отправки: настоящую подпись на сервере проверяет раннер,
а здесь проверяется ход маршрута. Двойник ведёт себя как ключи людей: у каждого свой ключ с паролем, плашка из
него, подпись это запись открепленной подписи над текущей фиксацией.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.entities import SigningIdentity
from hse_doc_studio.core.enums import DetachedFormat, DetachedOrigin, DetachedVerdict, SigningIdentityKind
from hse_doc_studio.core.signing_route.entities import DocSlot
from hse_doc_studio.core.value_objects import DetachedSignature, SignerInfo
from hse_doc_studio.use_cases.signatures._studio_signer import KeyPassphraseRequiredError
from hse_doc_studio.use_cases.signing_route.key_signer import (
    KeyInfo,
    KeyNotFoundError,
    KeyRequest,
    NoSigningKeyError,
    RouteKeySigner,
)
from hse_doc_studio.use_cases.signing_route.point import RoutePoint
from httpx2 import Response

from tests.fakes.signer_profile import make_png, make_self_signed
from tests.integration.api.signing_routes.stand import TOPIC, TOPIC_DOCS, Person, Project, Stand, make_project, person

PASSPHRASE = "correct horse"  # noqa: S105 — тестовое значение
PROPOSAL, APPLICATION = TOPIC_DOCS
PERSONAS = ("author", "supervisor", "academic_supervisor")
MODES = {"image": "image", "detached": "detached_text", "pades": "crypto_invisible"}
NAMES = {
    "author": "Иванов Иван Иванович",
    "supervisor": "Петров Пётр Петрович",
    "academic_supervisor": "Сидоров Сидор Сидорович",
}
PNG = make_png(120, 40)


# --- двойник ключей Студии -------------------------------------------------------------------------------------------


@dataclass
class FakeKeys:
    """Ключи людей: у кого есть ключ, тот подписывает им с паролем `PASSPHRASE`."""

    identities: dict[str, SigningIdentity] = field(default_factory=dict)
    broken: bool = False
    signed: list[tuple[str, DocSlot]] = field(default_factory=list)

    def give(self, who: Person, name: str) -> SigningIdentity:
        identity = SigningIdentity(
            id=uuid4(),
            label=f"Ключ {name}",
            kind=SigningIdentityKind.openpgp,
            subject_cn=name,
            not_after=datetime(2030, 1, 1, tzinfo=UTC),
            trusted=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            fingerprint=who.id.upper(),
            protected=True,
        )
        self.identities[who.id] = identity
        return identity

    def mine(self) -> SigningIdentity | None:
        return self.identities.get(require_actor().id or "")

    def find(self, identity_id: UUID | None) -> SigningIdentity:
        """Свой ключ по id или ключ по умолчанию; чужой и несуществующий неотличимы."""
        identity = self.mine()
        if identity is None:
            raise NoSigningKeyError
        if identity_id is not None and identity_id != identity.id:
            raise KeyNotFoundError
        return identity

    def signature(self, identity: SigningIdentity, pair: DocSlot, pdf_sha256: str) -> DetachedSignature:
        self.signed.append((identity.subject_cn, pair))
        return DetachedSignature(
            file=f".hse-studio/detached/{pair.doc_id}/{pair.slot_id}.asc",
            format=DetachedFormat.openpgp,
            origin=DetachedOrigin.studio,
            pdf_sha256=pdf_sha256,
            verdict=DetachedVerdict.valid,
            signer=identity.subject_cn,
            signer_id=identity.fingerprint or "",
            added_at=datetime.now(UTC).isoformat(),
        )

    def plate(self, identity: SigningIdentity) -> SignerInfo:
        fingerprint = identity.fingerprint or ""
        return SignerInfo(kind="openpgp", owner=identity.subject_cn, cert_id=fingerprint[:16], signer_id=fingerprint)


class _Installed:
    """Ключи текущего теста: подмены методов `RouteKeySigner` ниже читают их отсюда."""

    keys = FakeKeys()


async def _keys_allowed(self: RouteKeySigner) -> bool:
    return True


async def _default_key_info(self: RouteKeySigner) -> KeyInfo | None:
    identity = _Installed.keys.mine()
    if identity is None:
        return None
    return KeyInfo(identity.id, identity.label, identity.kind.value, protected=True, signer=identity.subject_cn)


async def _own_key(self: RouteKeySigner, identity_id: UUID) -> SigningIdentity:
    return _Installed.keys.find(identity_id)


async def _plate_of(self: RouteKeySigner, identity: SigningIdentity) -> SignerInfo:
    return _Installed.keys.plate(identity)


async def _default_plate(self: RouteKeySigner) -> SignerInfo | None:
    identity = _Installed.keys.mine()
    return _Installed.keys.plate(identity) if identity is not None else None


async def _check(self: RouteKeySigner, request: KeyRequest) -> SigningIdentity:
    identity = _Installed.keys.find(request.identity_id)
    if request.passphrase != PASSPHRASE:
        raise KeyPassphraseRequiredError
    return identity


async def _sign(
    self: RouteKeySigner, point: RoutePoint, pairs: Any, identity: SigningIdentity, passphrase: str
) -> tuple[DocSlot, ...]:
    keys = _Installed.keys
    if keys.broken:
        raise ValueError("gpg отказал в подписи: Bad passphrase")
    folder = point.project.folder
    state = self._signatures.get_state(folder)
    for pair in pairs:
        signature = keys.signature(identity, pair, state.frozen[pair.doc_id].sha256)
        detached = {**state.detached.get(pair.doc_id, {}), pair.slot_id: signature}
        state = replace(state, detached={**state.detached, pair.doc_id: detached})
    self._signatures.save_state(folder, state)
    return tuple(pairs)


_FAKES = {
    "keys_allowed": _keys_allowed,
    "default_key_info": _default_key_info,
    "own_key": _own_key,
    "plate_of": _plate_of,
    "default_plate": _default_plate,
    "check": _check,
    "sign": _sign,
}


def install_fake_keys(monkeypatch: pytest.MonkeyPatch) -> FakeKeys:
    keys = FakeKeys()
    monkeypatch.setattr(_Installed, "keys", keys)
    for name, fake in _FAKES.items():
        monkeypatch.setattr(RouteKeySigner, name, fake)
    return keys


# --- маршрут трёх человек --------------------------------------------------------------------------------------------


@dataclass
class Trio:
    stand: Stand
    project: Project
    people: dict[str, Person]
    route_id: str = ""

    @property
    def author(self) -> Person:
        return self.people["author"]

    @property
    def supervisor(self) -> Person:
        return self.people["supervisor"]

    @property
    def academic(self) -> Person:
        return self.people["academic_supervisor"]

    @property
    def url(self) -> str:
        return f"{self.project.routes}/{self.route_id}"

    # --- файлы проекта ---

    def state(self) -> dict[str, Any]:
        path = self.project.folder / ".hse-studio" / "signatures.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def withheld(self) -> dict[str, list[str]]:
        return {doc: sorted(slots) for doc, slots in self.state().get("withheld", {}).items() if slots}

    def frozen_sha(self) -> dict[str, str]:
        return {doc: frozen["sha256"] for doc, frozen in self.state().get("frozen", {}).items()}

    def signed_pdf_sha(self) -> dict[str, dict[str, str]]:
        """К какой фиксации относится каждая открепленная подпись: `документ -> слот -> sha`."""
        return {
            doc: {slot: sig["pdf_sha256"] for slot, sig in sigs.items()}
            for doc, sigs in self.state().get("detached", {}).items()
        }

    # --- автор ---

    def call(self, who: Person, method: str, path: str, **kwargs: Any) -> Response:
        return self.project.call(who, method, path, **kwargs)

    def route(self, who: Person | None = None) -> dict[str, Any]:
        resp = self.call(who or self.author, "GET", self.url)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def preview(self) -> dict[str, Any]:
        resp = self.call(self.author, "POST", f"{self.url}/preview", json={})
        assert resp.status_code == 200, resp.text
        return resp.json()

    def send(self, sign: dict[str, Any] | None = None) -> Response:
        expected = {d["doc_id"]: d["token"] for d in self.preview()["docs"]}
        return self.call(self.author, "POST", f"{self.url}/send", json={"expected": expected, "sign": sign})

    def sent(self, sign: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self.send(sign)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def put(self, steps: list[list[dict[str, Any]]], extra_slots: list[dict[str, str]] | None = None) -> None:
        body = {
            "steps": steps,
            "extra_slots": extra_slots or [],
            "deadline": None,
            "message": "Прошу подписать заявление до пятницы.",
        }
        updated = self.call(self.author, "PUT", self.url, json=body)
        assert updated.status_code == 200, updated.text

    def steps(self) -> list[dict[str, Any]]:
        """Участники маршрута как люди тела PUT, по порядку шагов."""
        return [
            {"id": p["id"], "persona": p["persona"], "user_id": p["user_id"], "invitation_id": p["invitation_id"]}
            for step in self.route()["steps"]
            for p in step
        ]

    def events(self) -> list[str]:
        return [e["kind"] for e in self.route()["events"]]

    # --- подписант ---

    def task(self, who: Person) -> dict[str, Any]:
        resp = self.call(who, "GET", f"{self.url}/task")
        assert resp.status_code == 200, resp.text
        return resp.json()

    def tokens(self, who: Person) -> dict[str, str]:
        return {d["doc_id"]: d["token"] for d in self.task(who)["docs"] if d["token"] is not None}

    def approve(
        self,
        who: Person,
        *,
        method: str | None = None,
        sign: dict[str, Any] | None = None,
        expected: dict[str, str] | None = None,
    ) -> Response:
        body = {"expected": self.tokens(who) if expected is None else expected, "method": method, "sign": sign}
        return self.call(who, "POST", f"{self.url}/task/approve", json=body)

    def approved(self, who: Person, **kwargs: Any) -> dict[str, Any]:
        resp = self.approve(who, **kwargs)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def sign(
        self, who: Person, *, passphrase: str | None = PASSPHRASE, expected: dict[str, str] | None = None
    ) -> Response:
        body = {
            "expected": self.tokens(who) if expected is None else expected,
            "identity_id": None,
            "passphrase": passphrase,
        }
        return self.call(who, "POST", f"{self.url}/task/sign", json=body)

    def signed(self, who: Person) -> dict[str, Any]:
        resp = self.sign(who)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def give_back(self, who: Person, comment: str = "Уточните цель проекта") -> Response:
        return self.call(who, "POST", f"{self.url}/task/return", json={"comment": comment})

    def image(self, who: Person, png: bytes = PNG, *, remember: bool = False) -> Response:
        return self.call(
            who,
            "POST",
            f"{self.url}/task/image",
            files={"file": ("signature.png", png, "image/png")},
            data={"remember": "true" if remember else "false"},
        )

    def plate_key(self, who: Person, identity_id: str) -> Response:
        return self.call(who, "PUT", f"{self.url}/task/plate", json={"identity_id": identity_id})

    def plate_file(self, who: Person, blob: bytes) -> Response:
        return self.call(
            who, "POST", f"{self.url}/task/plate/file", files={"file": ("cert.pem", blob, "application/x-pem-file")}
        )

    def profile_cert(self, who: Person, owner: str) -> None:
        """Сертификат в профиле подписанта: маршрут знает данные его плашки заранее (раздел 6.5)."""
        resp = self.stand.client.put(
            "/api/v1/account/signer-profile/public-key",
            headers=who.headers,
            files={"file": ("cert.pem", make_self_signed(owner).cert_pem, "application/x-pem-file")},
        )
        assert resp.status_code == 200, resp.text


def states(body: dict[str, Any]) -> list[str]:
    """Состояния участников по шагам, из хода маршрута или задачи."""
    return [p["state"] for step in body["steps"] for p in step]


def my(task: dict[str, Any]) -> tuple[str, str]:
    return task["me"]["state"], task["me"]["next_action"]


async def make_trio(
    stand: Stand,
    methods: dict[str, str] | None = None,
    *,
    images: tuple[str, ...] = ("author",),
    plates: tuple[str, ...] = (),
    profile_certs: tuple[str, ...] = (),
    academic: str = "slot",
) -> Trio:
    """Маршрут трёх человек до отправки.

    `methods` способ по персонам (по умолчанию картинка); `images` у кого картинка уже загружена автором;
    `plates` у кого подписант плашки записан в слот; `profile_certs` у кого сертификат лежит в профиле.
    `academic`: `slot` академрук подписывает заявление (необязательный слот), `approver` только согласует
    (участник без слотов), `none` академрука в маршруте нет.
    """
    chosen = dict.fromkeys(PERSONAS, "image") | (methods or {})
    people = {persona: await person(stand, NAMES[persona]) for persona in PERSONAS}
    author = people["author"]
    project = make_project(
        stand,
        author,
        supervisor={"name": NAMES["supervisor"], "role": "university"},
        academic_supervisor={"name": NAMES["academic_supervisor"], "role": "university"},
    )
    await project.member(people["supervisor"], "reviewer", "supervisor")
    if academic != "none":
        await project.member(people["academic_supervisor"], "reviewer", "academic_supervisor")
    trio = Trio(stand, project, people)
    for doc_id in TOPIC_DOCS:
        project.build(doc_id)
    for persona in PERSONAS if academic == "slot" else PERSONAS[:2]:
        _prepare_slot(trio, persona, chosen[persona], image=persona in images, plate=persona in plates)
        if persona in profile_certs:
            trio.profile_cert(people[persona], NAMES[persona])
    created = project.call(author, "POST", project.routes, json={"profile_id": TOPIC})
    assert created.status_code == 201, created.text
    trio.route_id = created.json()["id"]
    if academic == "slot":
        trio.put([[p] for p in trio.steps()], [{"doc_id": APPLICATION, "slot_id": "academic_supervisor"}])
    elif academic == "approver":
        approver = {"id": None, "persona": "academic_supervisor", "user_id": people["academic_supervisor"].id}
        trio.put([*([p] for p in trio.steps()), [{**approver, "invitation_id": None}]])
    return trio


def _prepare_slot(trio: Trio, slot_id: str, method: str, *, image: bool, plate: bool) -> None:
    """Слот автором до отправки: картинка, способ, подписант плашки и включённые размещения."""
    project, author = trio.project, trio.author
    slots = f"{project.base}/signatures/slots/{slot_id}"
    if image:
        project.png(author, slot_id)
    config = {"signing_identity_id": None, "sign_mode": MODES[method], "sign_reason": ""}
    _ok(project.call(author, "PATCH", f"{slots}/config", json=config))
    if plate:
        _ok(project.call(author, "PUT", f"{slots}/signer", json={"owner": NAMES[slot_id], "cert_id": "1A2B 3C4D"}))
    for doc_id in TOPIC_DOCS if slot_id == "supervisor" else (APPLICATION,):
        placement = f"{project.base}/signatures/placements/{doc_id}/{slot_id}"
        _ok(project.call(author, "PATCH", placement, json={"enabled": True}))


def _ok(resp: Response) -> None:
    assert resp.status_code == 200, resp.text
