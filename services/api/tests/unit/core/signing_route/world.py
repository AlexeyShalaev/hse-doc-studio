"""Проект в памяти для тестов маршрута: слоты, придержанные, фиксации и подписи, и прогон маршрута.

`World` держит то, что в настоящем проекте лежит в `.hse-studio/signatures.json`, собранных PDF и версиях на
подписи, и выполняет эффекты расчёта так, как их выполнят сценарии. `compiled` рабочая сборка («Собрать»),
`pinned` версия на подписи (раздел 12.3): пока она есть, это источник подписи. `Driver` ведёт маршрут: отправка на
кандидате со снятием версии на подписи, действия участников по `next_action`, после каждого шага эффекты, снимок,
применение расчёта и проверка, что повторный расчёт ничего не делает. Попутно проверяются инварианты раздела 2:
согласия по порядку шагов, картинка только после согласия этого документа, фиксация не сбрасывает поставленные
подписи.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from hse_doc_studio.core.enums import DetachedFormat, DetachedOrigin, DetachedVerdict, SignMode
from hse_doc_studio.core.signatures.plan import (
    CRYPTO_METHODS,
    DocFacts,
    SignMethod,
    VisibleMark,
    mark_of,
    method_of,
)
from hse_doc_studio.core.signing_route.effects import Effect, FillPlate, Freeze, Notify, Release, Withhold
from hse_doc_studio.core.signing_route.engine import Evaluation, RouteFacts, approved_docs, evaluate
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    NextAction,
    Notice,
    Participant,
    RouteStatus,
    SigningRoute,
)
from hse_doc_studio.core.signing_route.transitions import (
    apply_evaluation,
    approve,
    mark_notified,
    refresh_snapshot,
    send,
)
from hse_doc_studio.core.signing_route.versions import version_changes
from hse_doc_studio.core.value_objects import (
    DetachedSignature,
    EmbeddedSignature,
    FrozenPdf,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
    SignerInfo,
)

DOC = "topic_application"
DOC2 = "application"
BUILD = "b" * 64
T0 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def signer(owner: str) -> SignerInfo:
    return SignerInfo(kind="openpgp", owner=owner, cert_id="1A2B", signer_id=sha(owner))


@dataclass
class World:
    """Состояние подписей проекта и сборки документов."""

    modes: dict[str, SignMode]
    docs: tuple[str, ...] = (DOC,)
    slots: dict[str, SignatureSlot] = field(default_factory=dict)
    compiled: dict[str, str | None] = field(default_factory=dict)
    pinned: dict[str, str | None] = field(default_factory=dict)
    withheld: dict[str, set[str]] = field(default_factory=dict)
    frozen: dict[str, FrozenPdf] = field(default_factory=dict)
    detached: dict[str, dict[str, DetachedSignature]] = field(default_factory=dict)
    embedded: dict[str, dict[str, EmbeddedSignature]] = field(default_factory=dict)
    plates: dict[UUID, SignerInfo] = field(default_factory=dict)
    personas: dict[UUID, frozenset[str]] | None = None
    notices: list[Notify] = field(default_factory=list)
    resets: int = 0

    def __post_init__(self) -> None:
        for slot_id, mode in self.modes.items():
            self.slots.setdefault(slot_id, SignatureSlot("sig.png", 10, 4, sign_mode=mode))
        for doc_id in self.docs:
            self.compiled.setdefault(doc_id, BUILD)
            self.withheld.setdefault(doc_id, set())

    # --- факты ---

    def marks(self, doc_id: str) -> str:
        """Отпечаток видимого слоя без придержанных слотов, как `stamps_digest`."""
        items: list[str] = []
        for slot_id, slot in sorted(self.slots.items()):
            mark = mark_of(slot)
            if mark is VisibleMark.png and slot.png_path and slot_id not in self.withheld[doc_id]:
                items.append(f"png:{slot_id}:{slot.png_path}")
            elif mark is VisibleMark.plate:
                items.append(f"plate:{slot_id}:{slot.signer.owner if slot.signer else ''}")
        return sha("|".join(items))

    def state(self) -> SignaturesState:
        placement = SignaturePlacement(enabled=True, page=1, x_mm=10, y_mm=10, width_mm=30)
        return SignaturesState(
            slots=dict(self.slots),
            placements={doc_id: dict.fromkeys(self.slots, placement) for doc_id in self.docs},
            frozen=dict(self.frozen),
            detached={doc_id: dict(sigs) for doc_id, sigs in self.detached.items()},
            embedded={doc_id: dict(sigs) for doc_id, sigs in self.embedded.items()},
        )

    def source(self, doc_id: str) -> str | None:
        """Источник подписи (12.4): версия на подписи, если она есть (None: запись есть, файла нет), иначе сборка."""
        return self.pinned[doc_id] if doc_id in self.pinned else self.compiled[doc_id]

    def pin(self, doc_ids: Iterable[str]) -> None:
        """Снять версию на подписи из рабочей сборки, как сценарий отправки (12.3)."""
        for doc_id in doc_ids:
            if self.compiled[doc_id] is not None:
                self.pinned[doc_id] = self.compiled[doc_id]

    def doc_facts(self, doc_id: str) -> DocFacts:
        return DocFacts(self.source(doc_id), self.marks(doc_id), working_sha256=self.compiled[doc_id])

    def facts(self) -> RouteFacts:
        return RouteFacts(
            docs={doc_id: self.doc_facts(doc_id) for doc_id in self.docs},
            state=self.state(),
            withheld={doc_id: frozenset(slots) for doc_id, slots in self.withheld.items()},
            plates=dict(self.plates),
            personas=self.personas,
        )

    # --- эффекты и действия ---

    def apply(self, effects: Iterable[Effect]) -> None:
        for effect in effects:
            if isinstance(effect, Withhold):
                self.withheld[effect.doc_id].add(effect.slot_id)
            elif isinstance(effect, Release):
                self.withheld[effect.doc_id].discard(effect.slot_id)
            elif isinstance(effect, FillPlate):
                self.slots[effect.slot_id] = replace(self.slots[effect.slot_id], signer=effect.signer)
            elif isinstance(effect, Freeze):
                self.freeze(effect.doc_id)
            else:
                self.notices.append(effect)

    def freeze(self, doc_id: str) -> None:
        if self.detached.pop(doc_id, None) or self.embedded.pop(doc_id, None):
            self.resets += 1
        marks = self.marks(doc_id)
        build = self.source(doc_id) or ""
        self.frozen[doc_id] = FrozenPdf(
            path=f".hse-studio/frozen/{doc_id}.pdf",
            sha256=sha(f"B:{build}:{marks}"),
            source_sha256=build,
            size=1,
            frozen_at=T0.isoformat(),
            stamps_digest=marks,
        )

    def sign(self, pair: DocSlot) -> None:
        frozen = self.frozen[pair.doc_id]
        if method_of(self.slots[pair.slot_id].sign_mode) is SignMethod.pades:
            self.embedded.setdefault(pair.doc_id, {})[pair.slot_id] = EmbeddedSignature(
                field_name=pair.slot_id,
                base_sha256=frozen.sha256,
                revision_size=2,
                revision_sha256=sha(pair.slot_id),
                verdict=DetachedVerdict.valid,
                signer=pair.slot_id,
                signer_id=sha(pair.slot_id),
                added_at=T0.isoformat(),
            )
            return
        self.detached.setdefault(pair.doc_id, {})[pair.slot_id] = DetachedSignature(
            file=f".hse-studio/detached/{pair.doc_id}/{pair.slot_id}.asc",
            format=DetachedFormat.openpgp,
            origin=DetachedOrigin.studio,
            pdf_sha256=frozen.sha256,
            verdict=DetachedVerdict.valid,
            signer=pair.slot_id,
            signer_id=sha(pair.slot_id),
            added_at=T0.isoformat(),
        )

    def unsign(self, pair: DocSlot) -> None:
        self.detached.get(pair.doc_id, {}).pop(pair.slot_id, None)
        self.embedded.get(pair.doc_id, {}).pop(pair.slot_id, None)

    def is_signed(self, pair: DocSlot) -> bool:
        return pair.slot_id in self.detached.get(pair.doc_id, {}) or pair.slot_id in self.embedded.get(pair.doc_id, {})

    def is_crypto(self, pair: DocSlot) -> bool:
        return method_of(self.slots[pair.slot_id].sign_mode) in CRYPTO_METHODS

    def image_visible(self, pair: DocSlot) -> bool:
        return mark_of(self.slots[pair.slot_id]) is VisibleMark.png and pair.slot_id not in self.withheld[pair.doc_id]


def participant(step: int, persona: str, slots: Iterable[str] = (), *, docs: Iterable[str] = (DOC,)) -> Participant:
    """Участник с пользователем; `slots` его слоты на каждом из `docs`."""
    pairs = tuple(DocSlot(doc_id, slot_id) for doc_id in docs for slot_id in slots)
    return Participant(id=uuid4(), step=step, persona=persona, user_id=uuid4(), assignments=pairs)


def make_route(participants: Iterable[Participant], *, docs: tuple[str, ...] = (DOC,)) -> SigningRoute:
    return SigningRoute(
        id=uuid4(),
        project_id=uuid4(),
        profile_id="topic-approval",
        created_by=uuid4(),
        docs=docs,
        participants=tuple(participants),
    )


@dataclass
class Driver:
    """Ведёт маршрут, как сценарии: переход, расчёт, эффекты, снимок, применение, запомнить уведомления."""

    world: World
    route: SigningRoute
    actions: Counter[UUID] = field(default_factory=Counter)
    clock: datetime = T0

    def tick(self) -> datetime:
        self.clock += timedelta(minutes=1)
        return self.clock

    def evaluate(self) -> Evaluation:
        return evaluate(self.route, self.world.facts())

    def settle(self, *, notify: bool = True) -> Evaluation:
        """Выполнить расчёт и убедиться, что повторный расчёт ничего не делает."""
        evaluation = self.evaluate()
        effects = evaluation.effects if notify else tuple(e for e in evaluation.effects if not isinstance(e, Notify))
        self.world.apply(effects)
        at = self.tick()
        self.route = refresh_snapshot(apply_evaluation(self.route, evaluation, at=at), self.world.facts())
        for effect in effects:
            if isinstance(effect, Notify) and effect.notice is Notice.request and effect.outcome is not None:
                self.route = mark_notified(self.route, effect.participant_ids[0], effect.outcome, at=at)
        self._check_images()
        if notify:
            assert self.evaluate().effects == (), "расчёт после выполнения эффектов должен быть пустым"
        return evaluation

    def send(self, by: UUID) -> Evaluation:
        """Отправка, как сценарий R16: расчёт на кандидате, затем снятие версии на подписи изменившихся."""
        candidate = self.world.facts().candidate()
        changes = version_changes(self.route, candidate)
        self.route = send(self.route, candidate, by=by, at=self.tick())
        self.world.pin(changes.to_pin)
        return self.settle()

    def act(self, participant_id: UUID) -> NextAction:
        """Одно нажатие участника по его `next_action`; ключ для плашки он задаёт в том же действии."""
        action = self.evaluate().participant(participant_id).next_action
        if action in (NextAction.approve, NextAction.approve_and_sign):
            self._approve(participant_id, combined=action is NextAction.approve_and_sign)
        elif action is NextAction.sign:
            self._sign(participant_id)
        else:
            raise AssertionError(f"участнику нечего делать: {action}")
        self.actions[participant_id] += 1
        return action

    def run(self, limit: int = 30) -> None:
        """Действовать, пока маршрут идёт: первым по порядку шагов, кому есть что делать."""
        for _ in range(limit):
            if self.route.status is not RouteStatus.active:
                return
            waiting = [v for v in self.evaluate().participants if v.next_action in _ACTING]
            assert waiting, "идущий маршрут, в котором никто не может действовать"
            self.act(min(waiting, key=lambda v: v.step).participant_id)
        raise AssertionError("маршрут не завершился")

    def _approve(self, participant_id: UUID, *, combined: bool) -> None:
        p = self.route.participant(participant_id)
        if self.evaluate().participant(participant_id).needs_plate:
            assert p.user_id is not None
            for pair in p.assignments:
                if self.world.slots[pair.slot_id].signer is None:
                    self.world.slots[pair.slot_id] = replace(self.world.slots[pair.slot_id], signer=signer(p.persona))
            self.route = refresh_snapshot(self.route, self.world.facts())
        self._check_order(p)
        self.route = approve(self.route, self.world.facts(), participant_id, at=self.tick())
        # «Согласовать и подписать» один запрос: фиксация, подпись, затем уведомления.
        self.settle(notify=not combined)
        if combined:
            self._sign(participant_id)

    def _sign(self, participant_id: UUID) -> None:
        for pair in self.route.participant(participant_id).assignments:
            if self.world.is_crypto(pair) and not self.world.is_signed(pair):
                self.world.sign(pair)
        self.settle()

    def _check_order(self, p: Participant) -> None:
        """Инвариант 1: шаг k согласует только после всех шагов до k, на текущие версии их документов."""
        facts = self.world.facts()
        for other in self.route.participants:
            if other.step < p.step:
                docs = other.doc_ids(self.route.docs)
                assert approved_docs(self.route, other, facts) == frozenset(docs), "согласие вне очереди"

    def _check_images(self) -> None:
        """Инвариант 2: картинка на документе видна только у согласовавшего версию на подписи этого документа."""
        facts = self.world.facts()
        for p in self.route.participants:
            approved = approved_docs(self.route, p, facts)
            for pair in p.assignments:
                visible = self.world.image_visible(pair)
                assert pair.doc_id in approved or not visible, f"картинка {pair} видна до согласия"


_ACTING = frozenset({NextAction.approve, NextAction.approve_and_sign, NextAction.sign})


def by_persona(route: SigningRoute) -> Mapping[str, Participant]:
    return {p.persona: p for p in route.participants}
