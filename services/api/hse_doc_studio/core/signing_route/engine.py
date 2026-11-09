"""Расчёт маршрута подписания (docs/design/signing-route.md, разделы 4 и 5).

`evaluate(route, facts)` чистая функция. По маршруту и тому, что известно о документах сейчас, она отвечает: в
какой фазе маршрут, где граница L, чья очередь и что делать каждому, надо ли остановить или завершить маршрут и
какие эффекты выполнить. Ничего не пишет. Эффекты это разница между нужным и текущим, поэтому расчёт после их
выполнения (и `transitions.refresh_snapshot`) эффектов не даёт.

Термины раздела 4.2:
- участник меняет видимый слой, пока его картинка не встала (нет согласия текущей версии) или у его плашки нет
  данных подписанта; L это последний шаг с таким участником, 0 если таких нет;
- пока они есть, фаза `approval`: согласия строго по шагам, картинка встаёт при согласии;
- когда их не осталось, видимый слой окончателен: фаза `signing`, документы с ЭП фиксируются, согласившие до
  фиксации подписывают параллельно, следующие шаги согласуют и подписывают по порядку одним действием.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from uuid import UUID

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signatures.plan import (
    CRYPTO_METHODS,
    DocFacts,
    SlotStatus,
    VisibleMark,
    frozen_is_current,
    mark_of,
    method_of,
    slot_state,
)
from hse_doc_studio.core.signing_route.effects import Effect, FillPlate, Freeze, Notify, Release, Withhold
from hse_doc_studio.core.signing_route.entities import (
    HOLDING_STATUSES,
    WATCHING_STATUSES,
    DocSlot,
    DocSnapshot,
    NextAction,
    Notice,
    Participant,
    ParticipantState,
    RequestOutcome,
    RoutePhase,
    RouteStatus,
    SigningRoute,
    StopReason,
)
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo

_UNBUILT = DocFacts(compiled_sha256=None, marks_digest="")


def approval_token(facts: DocFacts) -> str:
    """Отпечаток версии документа, которую согласует человек: `build:<хэш сборки>` (раздел 7)."""
    return f"build:{facts.compiled_sha256 or ''}"


@dataclass(frozen=True)
class RouteFacts:
    """Что известно о документах маршрута сейчас.

    - `docs`: факты сборки каждого документа маршрута (`DocFacts` плана подписей). `marks_digest` отпечаток
      видимого слоя без придержанных слотов, то есть того, что поставила бы фиксация сейчас;
    - `state`: состояние подписей проекта (способы и плашки слотов, фиксации, открепленные и встроенные ЭП);
    - `withheld`: придержанные слоты по документам (`SignaturesState.withheld`, раздел 6.1);
    - `plates`: известные данные плашки по пользователям: открытая часть ключа по умолчанию или сертификат из
      профиля (раздел 6.5); закрытых ключей здесь нет;
    - `personas`: персоны участников проекта по пользователям, чтобы заметить ушедшего; None: не проверять.
    """

    docs: Mapping[str, DocFacts]
    state: SignaturesState
    withheld: Mapping[str, Collection[str]] = field(default_factory=dict)
    plates: Mapping[UUID, SignerInfo] = field(default_factory=dict)
    personas: Mapping[UUID, Collection[str]] | None = None

    def doc(self, doc_id: str) -> DocFacts:
        """Факты документа; документ без фактов считается несобранным."""
        return self.docs.get(doc_id, _UNBUILT)

    def frozen_sha256(self, doc_id: str) -> str | None:
        frozen = self.state.frozen.get(doc_id)
        return frozen.sha256 if frozen is not None else None

    def is_withheld(self, pair: DocSlot) -> bool:
        return pair.slot_id in self.withheld.get(pair.doc_id, ())

    def tokens(self, doc_ids: Iterable[str]) -> dict[str, str]:
        """Отпечатки согласия по документам (`approval_token`)."""
        return {doc_id: approval_token(self.doc(doc_id)) for doc_id in doc_ids}

    def snapshot(self, doc_ids: Iterable[str]) -> dict[str, DocSnapshot]:
        """Текущие отпечатки документов, как их хранит снимок маршрута."""
        return {
            doc_id: DocSnapshot(
                compiled_sha256=self.doc(doc_id).compiled_sha256,
                marks_digest=self.doc(doc_id).marks_digest,
                frozen_sha256=self.frozen_sha256(doc_id),
            )
            for doc_id in doc_ids
        }


@dataclass(frozen=True)
class ParticipantView:
    """Расчёт по участнику.

    `remaining_actions` сколько ещё нажатий от него нужно (таблица 4.4; 2 значит «согласовать, затем подписать
    итоговый PDF», а при равных шансах в параллельном шаге это верхняя граница). `changes_visible` он ещё меняет
    видимый слой (входит в L). `needs_image` и `needs_plate` до согласия нужно загрузить картинку или задать ключ
    для плашки.
    """

    participant_id: UUID
    step: int
    state: ParticipantState
    next_action: NextAction
    remaining_actions: int
    changes_visible: bool
    needs_image: bool = False
    needs_plate: bool = False


@dataclass(frozen=True)
class Evaluation:
    """Итог расчёта маршрута.

    `status` каким маршрут должен стать: `paused` при остановке (`stop`, `stopped_by`), `completed` когда все
    сделали своё, `active` если у завершённого пропала подпись; иначе прежний. `phase` задана у `active` и
    `completed`. `last_visible_step` это L. `current_step` первый непройденный шаг (None: все пройдены).
    """

    status: RouteStatus
    phase: RoutePhase | None
    last_visible_step: int
    current_step: int | None
    steps: tuple[int, ...]
    participants: tuple[ParticipantView, ...]
    stop: StopReason | None = None
    stopped_by: UUID | None = None
    effects: tuple[Effect, ...] = ()

    def participant(self, participant_id: UUID) -> ParticipantView:
        for view in self.participants:
            if view.participant_id == participant_id:
                return view
        raise KeyError(participant_id)

    @property
    def step_position(self) -> int | None:
        """Номер текущего шага по порядку, с 1: «шаг k из n», где n это `len(steps)`."""
        if self.current_step is None:
            return None
        return self.steps.index(self.current_step) + 1


@dataclass(frozen=True)
class _Info:
    """Что известно об участнике в этом расчёте."""

    participant: Participant
    png: tuple[DocSlot, ...]  # пары с картинкой: придержаны до его согласия
    plates: tuple[DocSlot, ...]  # пары с плашкой открепленной ЭП
    unsigned: tuple[DocSlot, ...]  # пары с ЭП, которые ещё не `signed`
    crypto_docs: frozenset[str]
    missing_plate: tuple[str, ...]  # слоты плашек без данных подписанта
    missing_image: tuple[str, ...]  # слоты картинок без загруженной картинки
    approval_valid: bool  # согласие этого раунда на текущие сборки его документов

    @property
    def approved(self) -> bool:
        return self.approval_valid and not self.missing_plate

    @property
    def done(self) -> bool:
        return self.approved and not self.unsigned

    @property
    def changer(self) -> bool:
        return not self.approved and bool(self.png or self.missing_plate)

    @property
    def early(self) -> bool:
        """Согласовал до фиксации: его ЭП запрашивается после неё и не держит следующие шаги."""
        approval = self.participant.approval
        return approval is not None and approval.phase is RoutePhase.approval


@dataclass(frozen=True)
class _Progress:
    """Где маршрут, без учёта статуса: фаза, L, текущий шаг, кто ещё меняет видимый слой."""

    phase: RoutePhase
    last_visible_step: int
    current_step: int | None
    changers: tuple[UUID, ...]
    last_changers: tuple[UUID, ...]  # меняющие видимый слой на шаге L


def evaluate(route: SigningRoute, facts: RouteFacts) -> Evaluation:
    """Фаза, L, ход каждого участника, остановка и эффекты маршрута по текущим фактам."""
    infos = tuple(_info(route, p, facts) for p in route.participants)
    stop, stopped_by = _stop(route, facts)
    status = _target_status(route, infos, stop)
    progress = _progress(route, infos)
    views = tuple(_view(route, info, status, progress) for info in infos)
    return Evaluation(
        status=status,
        phase=_phase(status, progress),
        last_visible_step=progress.last_visible_step,
        current_step=progress.current_step,
        steps=route.steps,
        participants=views,
        stop=stop,
        stopped_by=stopped_by,
        effects=_effects(route, facts, infos, views, status, progress, stop),
    )


def notice_for(route: SigningRoute, notice: Notice) -> Notify:
    """Кому уведомление о событии маршрута (разделы 5.4 и 6.6). Запрос и напоминание адресные, их здесь нет.

    - `completed`: автору и всем участникам;
    - `paused`, `returned`: автору и тем, кто уже согласовал в этом раунде;
    - `cancelled`: тем, кому в этом раунде приходил запрос.
    """
    if notice is Notice.completed:
        return Notify(notice, tuple(p.id for p in route.participants), sender=True)
    if notice in (Notice.paused, Notice.returned):
        acted = tuple(p.id for p in route.participants if p.approval is not None and p.approval.round == route.round)
        return Notify(notice, acted, sender=True)
    if notice is Notice.cancelled:
        asked = tuple(p.id for p in route.participants if p.notified is not None and p.notified.round == route.round)
        return Notify(notice, asked)
    raise ValueError(f"{notice} is addressed to one participant")


# --- участник ---------------------------------------------------------------------------------------------------


def _info(route: SigningRoute, p: Participant, facts: RouteFacts) -> _Info:
    png, plates, crypto = _classify(p.assignments, facts.state)
    return _Info(
        participant=p,
        png=png,
        plates=plates,
        unsigned=tuple(pair for pair in crypto if not _signed(pair, facts)),
        crypto_docs=frozenset(pair.doc_id for pair in crypto),
        missing_plate=tuple(dict.fromkeys(pair.slot_id for pair in plates if not _plate_known(pair, p, facts))),
        missing_image=tuple(dict.fromkeys(pair.slot_id for pair in png if not _image_ready(pair, facts))),
        approval_valid=_approval_valid(route, p, facts),
    )


def _classify(
    pairs: tuple[DocSlot, ...], state: SignaturesState
) -> tuple[tuple[DocSlot, ...], tuple[DocSlot, ...], tuple[DocSlot, ...]]:
    """Пары по видимой метке (картинка, плашка) и пары с ЭП; способ берётся из слота."""
    png: list[DocSlot] = []
    plates: list[DocSlot] = []
    crypto: list[DocSlot] = []
    for pair in pairs:
        slot = state.slots.get(pair.slot_id)
        mark = mark_of(slot)
        if mark is VisibleMark.png:
            png.append(pair)
        elif mark is VisibleMark.plate:
            plates.append(pair)
        if method_of(slot.sign_mode if slot is not None else SignMode.image) in CRYPTO_METHODS:
            crypto.append(pair)
    return tuple(png), tuple(plates), tuple(crypto)


def _signed(pair: DocSlot, facts: RouteFacts) -> bool:
    return slot_state(facts.state, pair.doc_id, pair.slot_id, facts.doc(pair.doc_id)).status is SlotStatus.signed


def _plate_known(pair: DocSlot, p: Participant, facts: RouteFacts) -> bool:
    """Данные плашки есть в слоте или их даст известный ключ участника при фиксации."""
    slot = facts.state.slots.get(pair.slot_id)
    if slot is not None and slot.signer is not None:
        return True
    return p.user_id is not None and p.user_id in facts.plates


def _image_ready(pair: DocSlot, facts: RouteFacts) -> bool:
    slot = facts.state.slots.get(pair.slot_id)
    return slot is not None and slot.png_path is not None and facts.doc(pair.doc_id).png_exists(slot.png_path)


def _approval_valid(route: SigningRoute, p: Participant, facts: RouteFacts) -> bool:
    approval = p.approval
    if approval is None or approval.round != route.round:
        return False
    return all(approval.tokens.get(doc_id) == approval_token(facts.doc(doc_id)) for doc_id in p.doc_ids(route.docs))


# --- остановка и статус -------------------------------------------------------------------------------------------

_STOP_PRIORITY = (StopReason.rebuilt, StopReason.frozen_changed, StopReason.marks_changed)


def _stop(route: SigningRoute, facts: RouteFacts) -> tuple[StopReason | None, UUID | None]:
    """Что останавливает маршрут: изменение документа (таблица 5.5) у идущего и завершённого, уход участника
    только у идущего: завершённому подписи уже поставлены."""
    if route.status not in WATCHING_STATUSES:
        return None, None
    now = facts.snapshot(route.docs)
    reasons = {_doc_change(route.snapshot.get(doc_id), now[doc_id]) for doc_id in route.docs}
    reason = next((r for r in _STOP_PRIORITY if r in reasons), None)
    if reason is not None:
        return reason, None
    left = _left(route, facts)
    return (StopReason.participant_left, left) if left is not None else (None, None)


def _doc_change(seen: DocSnapshot | None, now: DocSnapshot) -> StopReason | None:
    if seen is None or seen.compiled_sha256 != now.compiled_sha256:
        return StopReason.rebuilt
    if seen.frozen_sha256 != now.frozen_sha256:
        return StopReason.frozen_changed
    if seen.marks_digest != now.marks_digest:
        return StopReason.marks_changed
    return None


def _left(route: SigningRoute, facts: RouteFacts) -> UUID | None:
    """Участник, который больше не в проекте или потерял персону своего шага."""
    if facts.personas is None or route.status is not RouteStatus.active:
        return None
    for p in route.participants:
        if p.user_id is not None and p.persona not in facts.personas.get(p.user_id, ()):
            return p.id
    return None


def _target_status(route: SigningRoute, infos: tuple[_Info, ...], stop: StopReason | None) -> RouteStatus:
    if stop is not None:
        return RouteStatus.paused
    all_done = all(info.done for info in infos)
    if route.status is RouteStatus.active and all_done:
        return RouteStatus.completed
    if route.status is RouteStatus.completed and not all_done:
        # Подпись слота пропала или стала недействительной: ждём только её, маршрут не останавливается (5.5).
        return RouteStatus.active
    return route.status


def _phase(status: RouteStatus, progress: _Progress) -> RoutePhase | None:
    if status is RouteStatus.completed:
        return RoutePhase.done
    if status is RouteStatus.active:
        return progress.phase
    return None


# --- ход ------------------------------------------------------------------------------------------------------------


def _progress(route: SigningRoute, infos: tuple[_Info, ...]) -> _Progress:
    changers = tuple(info for info in infos if info.changer)
    phase = RoutePhase.approval if changers else RoutePhase.signing
    last = max((info.participant.step for info in changers), default=0)
    current = next(
        (
            step
            for step in route.steps
            if not all(_settled(info, phase) for info in infos if info.participant.step == step)
        ),
        None,
    )
    return _Progress(
        phase=phase,
        last_visible_step=last,
        current_step=current,
        changers=tuple(info.participant.id for info in changers),
        last_changers=tuple(info.participant.id for info in changers if info.participant.step == last),
    )


def _settled(info: _Info, phase: RoutePhase) -> bool:
    """Участник сделал всё, что было возможно: до фиксации согласовал, после фиксации согласовал и подписал."""
    if not info.approved:
        return False
    return phase is RoutePhase.approval or info.early or not info.unsigned


def _view(route: SigningRoute, info: _Info, status: RouteStatus, progress: _Progress) -> ParticipantView:
    state = _state(route, info, status, progress)
    return ParticipantView(
        participant_id=info.participant.id,
        step=info.participant.step,
        state=state,
        next_action=_action(state, info, progress),
        remaining_actions=_remaining(info, progress),
        changes_visible=info.changer,
        needs_image=bool(info.missing_image),
        needs_plate=bool(info.missing_plate),
    )


def _state(route: SigningRoute, info: _Info, status: RouteStatus, progress: _Progress) -> ParticipantState:
    p = info.participant
    if status is RouteStatus.returned and route.stopped_by == p.id:
        return ParticipantState.returned
    if p.user_id is None:
        return ParticipantState.invited
    if info.done:
        return ParticipantState.done
    if status is not RouteStatus.active:
        return ParticipantState.waiting
    return _turn_state(info, progress)


def _turn_state(info: _Info, progress: _Progress) -> ParticipantState:
    signing = progress.phase is RoutePhase.signing
    if info.approved:
        return ParticipantState.to_sign if signing else ParticipantState.waiting
    if info.participant.step != progress.current_step:
        return ParticipantState.waiting
    if signing and info.unsigned:
        return ParticipantState.to_approve_sign
    return ParticipantState.to_approve


_ACTIONS = {
    ParticipantState.invited: NextAction.wait,
    ParticipantState.waiting: NextAction.wait,
    ParticipantState.returned: NextAction.wait,
    ParticipantState.to_approve: NextAction.approve,
    ParticipantState.to_approve_sign: NextAction.approve_and_sign,
    ParticipantState.to_sign: NextAction.sign,
    ParticipantState.done: NextAction.done,
}


def _action(state: ParticipantState, info: _Info, progress: _Progress) -> NextAction:
    # Последний, кто меняет видимый слой, совмещает: после его согласия сервер фиксирует и подписывает (4.2).
    if state is ParticipantState.to_approve and info.unsigned and progress.changers == (info.participant.id,):
        return NextAction.approve_and_sign
    return _ACTIONS[state]


def _remaining(info: _Info, progress: _Progress) -> int:
    """Сколько нажатий ещё нужно от участника (таблица 4.4)."""
    if info.done:
        return 0
    if info.approved or not info.unsigned or progress.phase is RoutePhase.signing:
        return 1
    if info.participant.step > progress.last_visible_step or progress.last_changers == (info.participant.id,):
        return 1
    return 2


# --- эффекты ----------------------------------------------------------------------------------------------------------


def _effects(
    route: SigningRoute,
    facts: RouteFacts,
    infos: tuple[_Info, ...],
    views: tuple[ParticipantView, ...],
    status: RouteStatus,
    progress: _Progress,
    stop: StopReason | None,
) -> tuple[Effect, ...]:
    # Черновик ещё ничего не трогал, отменённый и снятый с контроля оставляют всё как есть (5.6).
    if route.status not in HOLDING_STATUSES:
        return ()
    files: list[Effect] = list(_image_effects(infos, facts))
    if status is RouteStatus.active and progress.phase is RoutePhase.signing:
        files += _freeze_effects(route, facts, infos, files)
    return (*files, *_notices(route, infos, views, status, stop))


def _image_effects(infos: tuple[_Info, ...], facts: RouteFacts) -> list[Withhold | Release]:
    """Картинка участника видна, только пока его согласие относится к текущей сборке (инвариант 2)."""
    effects: list[Withhold | Release] = []
    for info in infos:
        for pair in info.png:
            held = facts.is_withheld(pair)
            if info.approval_valid and held:
                effects.append(Release(pair.doc_id, pair.slot_id, info.participant.id))
            elif not info.approval_valid and not held:
                effects.append(Withhold(pair.doc_id, pair.slot_id))
    return effects


def _freeze_effects(
    route: SigningRoute, facts: RouteFacts, infos: tuple[_Info, ...], earlier: list[Effect]
) -> list[Effect]:
    """Видимый слой окончателен: заполнить плашки известными ключами и зафиксировать документы с ЭП (6.2)."""
    fills = _plate_fills(infos, facts)
    filled = {fill.slot_id for fill in fills}
    touched = {e.doc_id for e in earlier if isinstance(e, Withhold | Release)}
    touched |= {pair.doc_id for info in infos for pair in info.plates if pair.slot_id in filled}
    crypto_docs = {doc_id for info in infos for doc_id in info.crypto_docs}
    freezes = [
        Freeze(doc_id)
        for doc_id in route.docs
        if doc_id in crypto_docs and (doc_id in touched or not _frozen_current(doc_id, facts))
    ]
    return [*fills, *freezes]


def _plate_fills(infos: tuple[_Info, ...], facts: RouteFacts) -> list[FillPlate]:
    fills: dict[str, FillPlate] = {}
    for info in infos:
        signer = _known_signer(info.participant, facts)
        if signer is None:
            continue
        for pair in info.plates:
            slot = facts.state.slots.get(pair.slot_id)
            if slot is not None and slot.signer is None:
                fills.setdefault(pair.slot_id, FillPlate(pair.slot_id, info.participant.id, signer))
    return list(fills.values())


def _known_signer(p: Participant, facts: RouteFacts) -> SignerInfo | None:
    return facts.plates.get(p.user_id) if p.user_id is not None else None


def _frozen_current(doc_id: str, facts: RouteFacts) -> bool:
    frozen = facts.state.frozen.get(doc_id)
    return frozen is not None and frozen_is_current(frozen, facts.doc(doc_id)) is None


_OUTCOMES = {
    NextAction.approve: RequestOutcome.approve,
    NextAction.approve_and_sign: RequestOutcome.approve_sign,
    NextAction.sign: RequestOutcome.sign,
}


def _notices(
    route: SigningRoute,
    infos: tuple[_Info, ...],
    views: tuple[ParticipantView, ...],
    status: RouteStatus,
    stop: StopReason | None,
) -> list[Notify]:
    if stop is StopReason.participant_left:
        # «Назначьте другого подписанта»: это решает только автор (раздел 5.4).
        return [Notify(Notice.paused, sender=True)]
    if status is RouteStatus.paused and route.status is not RouteStatus.paused:
        return [notice_for(route, Notice.paused)]
    if status is RouteStatus.completed and route.status is not RouteStatus.completed:
        return [notice_for(route, Notice.completed)]
    if status is not RouteStatus.active:
        return []
    requests: list[Notify] = []
    for info, view in zip(infos, views, strict=True):
        outcome = _OUTCOMES.get(view.next_action)
        if outcome is not None and _should_request(route, info, outcome):
            requests.append(Notify(Notice.request, (info.participant.id,), outcome=outcome))
    return requests


def _should_request(route: SigningRoute, info: _Info, outcome: RequestOutcome) -> bool:
    """Запрос приходит раз за раунд на согласие и раз на «подпишите итоговый PDF»."""
    # Согласовавший после фиксации сейчас сам подписывает на странице: второе уведомление ему не нужно.
    if outcome is RequestOutcome.sign and not info.early:
        return False
    last = info.participant.notified
    return last is None or last.round != route.round or _turn(last.outcome) is not _turn(outcome)


def _turn(outcome: RequestOutcome) -> RequestOutcome:
    return RequestOutcome.sign if outcome is RequestOutcome.sign else RequestOutcome.approve
