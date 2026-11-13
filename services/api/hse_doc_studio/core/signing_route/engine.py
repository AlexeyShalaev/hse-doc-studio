"""Расчёт маршрута подписания (docs/design/signing-route.md, разделы 4 и 5).

`evaluate(route, facts)` чистая функция. По маршруту и тому, что известно о документах сейчас, она отвечает: в
какой фазе маршрут, где граница L, чья очередь и что делать каждому, надо ли остановить или завершить маршрут и
какие эффекты выполнить. Ничего не пишет. Эффекты это разница между нужным и текущим, поэтому расчёт после их
выполнения (и `transitions.refresh_snapshot`) эффектов не даёт.

Термины раздела 4.2:
- участник меняет видимый слой, пока его картинка не встала (нет согласия текущей версии) или у его плашки нет
  данных подписанта; L это последний шаг с таким участником, 0 если таких нет;
- согласие действует по документам (раздел 12.6): картинка участника на документе открыта, пока совпадает
  отпечаток этого документа, а для хода шагов участник согласовал, только если совпали отпечатки всех его
  документов;
- метки даты слота (раздел 14.4) тоже меняют видимый слой: дата появится при согласии, поэтому участник с метками
  даты меняет видимый слой, пока не согласовал;
- пока они есть, фаза `approval`: согласия строго по шагам, картинка встаёт при согласии;
- когда их не осталось, видимый слой окончателен: фаза `signing`, документы с ЭП фиксируются, согласившие до
  фиксации подписывают параллельно, следующие шаги согласуют и подписывают по порядку одним действием.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field, replace
from uuid import UUID

from hse_doc_studio.core.enums import SignedAtSource, SignMode
from hse_doc_studio.core.signatures.dates import display_day
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
from hse_doc_studio.core.signing_route.effects import (
    Effect,
    FillPlate,
    Freeze,
    Notify,
    RecordSignedAt,
    Release,
    Skip,
    Unskip,
    Withhold,
)
from hse_doc_studio.core.signing_route.entities import (
    HOLDING_STATUSES,
    TURN_STATES,
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
    SkipBlocker,
    StopReason,
)
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo, SkippedSlot

_UNBUILT = DocFacts(compiled_sha256=None, marks_digest="")


def approval_token(facts: DocFacts) -> str:
    """Отпечаток версии документа, которую согласует человек: `build:<sha256 источника подписи>` (разделы 7 и 12.4).

    Источник подписи это версия на подписи, если она есть, иначе текущая сборка (`DocFacts.compiled_sha256`); у
    кандидата новой версии (`RouteFacts.candidate`) текущая сборка.
    """
    return f"build:{facts.compiled_sha256 or ''}"


@dataclass(frozen=True)
class RouteFacts:
    """Что известно о документах маршрута сейчас.

    - `docs`: факты каждого документа маршрута (`DocFacts` плана подписей). `compiled_sha256` sha256 источника
      подписи (версии на подписи, если она есть, 12.4), `working_sha256` текущей сборки. `marks_digest`
      отпечаток видимого слоя без придержанных слотов, то есть того, что поставила бы фиксация сейчас;
    - `state`: состояние подписей проекта (способы и плашки слотов, фиксации, открепленные и встроенные ЭП);
    - `withheld`: придержанные слоты по документам (`SignaturesState.withheld`, раздел 6.1);
    - `plates`: известные данные плашки по пользователям: открытая часть ключа по умолчанию или сертификат из
      профиля (раздел 6.5); закрытых ключей здесь нет;
    - `personas`: персоны участников проекта по пользователям, чтобы заметить ушедшего; None: не проверять;
    - `optional`: необязательные подписи по документам на точке маршрута (`SignaturesState.optional[doc][профиль]`,
      раздел 13.3): их можно пропустить;
    - `skipped`: пропущенные подписи (`SignaturesState.skipped`, раздел 13.3), отдельным полем, как `withheld`:
      расчёт сверяет с ними пропуски участников и даёт эффекты `Skip` и `Unskip`.
    """

    docs: Mapping[str, DocFacts]
    state: SignaturesState
    withheld: Mapping[str, Collection[str]] = field(default_factory=dict)
    plates: Mapping[UUID, SignerInfo] = field(default_factory=dict)
    personas: Mapping[UUID, Collection[str]] | None = None
    optional: Mapping[str, Collection[str]] = field(default_factory=dict)
    skipped: Mapping[str, Mapping[str, SkippedSlot]] = field(default_factory=dict)

    def doc(self, doc_id: str) -> DocFacts:
        """Факты документа; документ без фактов считается несобранным."""
        return self.docs.get(doc_id, _UNBUILT)

    def candidate(self) -> RouteFacts:
        """Кандидат новой версии (раздел 12.6): источник каждого документа заменён его текущей сборкой.

        На кандидате считают предпросмотр и отправку: `compiled_sha256 = working_sha256`. Документ без сборки
        остаётся со своей версией на подписи; несобранным (`not_built`) кандидат считает только документ без
        того и другого. Остальное (видимый слой, состояние подписей, придержанные, плашки, персоны) то же.
        """
        docs = {
            doc_id: replace(doc, compiled_sha256=doc.working_sha256) if doc.working_sha256 is not None else doc
            for doc_id, doc in self.docs.items()
        }
        return replace(self, docs=docs)

    def frozen_sha256(self, doc_id: str) -> str | None:
        frozen = self.state.frozen.get(doc_id)
        return frozen.sha256 if frozen is not None else None

    def is_withheld(self, pair: DocSlot) -> bool:
        return pair.slot_id in self.withheld.get(pair.doc_id, ())

    def is_optional(self, pair: DocSlot) -> bool:
        return pair.slot_id in self.optional.get(pair.doc_id, ())

    def skip_record(self, pair: DocSlot) -> SkippedSlot | None:
        return self.skipped.get(pair.doc_id, {}).get(pair.slot_id)

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
class SkipOption:
    """Можно ли пропустить участника сейчас и что это даст (раздел 13.6, `RouteParticipant.skip`).

    `pairs` оставшиеся неподписанные пары, которые пропуск снимет; `required` среди них обязательные (мешают,
    `blocker` `required_slots`). `keeps_marks` документы, где метка пропущенного останется в зафиксированном PDF с
    ЭП; `refreezes` документы, которые маршрут зафиксирует заново без метки (13.5).
    """

    available: bool
    blocker: SkipBlocker | None = None
    pairs: tuple[DocSlot, ...] = ()
    required: tuple[DocSlot, ...] = ()
    keeps_marks: tuple[str, ...] = ()
    refreezes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParticipantView:
    """Расчёт по участнику.

    `remaining_actions` сколько ещё нажатий от него нужно (таблица 4.4; 2 значит «согласовать, затем подписать
    итоговый PDF», а при равных шансах в параллельном шаге это верхняя граница). `changes_visible` он ещё меняет
    видимый слой (входит в L). `needs_image` и `needs_plate` до согласия нужно загрузить картинку или задать ключ
    для плашки. `approved` согласие этого раунда действует по всем его документам (его показывают как
    `approved_at`); `approved_docs` документы, по которым оно действует (12.6): после новой версии согласие
    перенесено, но на изменившемся документе уже не действует.
    """

    participant_id: UUID
    step: int
    state: ParticipantState
    next_action: NextAction
    remaining_actions: int
    changes_visible: bool
    needs_image: bool = False
    needs_plate: bool = False
    approved: bool = False
    approved_docs: frozenset[str] = frozenset()
    skip: SkipOption = field(default_factory=lambda: SkipOption(False))


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
    approved_docs: frozenset[str]  # его документы, чей отпечаток совпал с согласием этого раунда (12.6)
    approval_valid: bool  # согласие этого раунда на версии на подписи всех его документов
    skipped: bool = False  # автор пропустил его в этом раунде (13.3): пропущенные пары в остальных полях не учтены
    dated: tuple[DocSlot, ...] = ()  # пары с метками даты (14.4): дата встанет при его согласии

    @property
    def approved(self) -> bool:
        return self.approval_valid and not self.missing_plate

    @property
    def done(self) -> bool:
        return self.skipped or (self.approved and not self.unsigned)

    @property
    def changer(self) -> bool:
        """Ещё меняет видимый слой (4.2): картинка, плашка без данных или метки даты (14.4) встанут при согласии."""
        return not self.skipped and not self.approved and bool(self.png or self.missing_plate or self.dated)

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
    views = tuple(_view(route, info, status, progress, facts) for info in infos)
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


def skipped_pairs(route: SigningRoute, p: Participant) -> frozenset[DocSlot]:
    """Пары, которые автор пропустил у участника в этом раунде (13.3); пусто, если его не пропускали."""
    skip = p.skipped
    return frozenset(skip.pairs) if skip is not None and skip.round == route.round else frozenset()


def _is_skipped(route: SigningRoute, p: Participant) -> bool:
    return p.skipped is not None and p.skipped.round == route.round


def _info(route: SigningRoute, p: Participant, facts: RouteFacts) -> _Info:
    # Пропущенные пары выпадают из расчёта явно: состояние подписей отвечает им `skipped`, но не `signed` (13.3).
    skipped = skipped_pairs(route, p)
    pairs = tuple(pair for pair in p.assignments if pair not in skipped)
    png, plates, crypto = _classify(pairs, facts.state)
    approved = approved_docs(route, p, facts)
    return _Info(
        participant=p,
        png=png,
        plates=plates,
        unsigned=tuple(pair for pair in crypto if not _signed(pair, facts)),
        crypto_docs=frozenset(pair.doc_id for pair in crypto),
        missing_plate=tuple(dict.fromkeys(pair.slot_id for pair in plates if not _plate_known(pair, p, facts))),
        missing_image=tuple(dict.fromkeys(pair.slot_id for pair in png if not _image_ready(pair, facts))),
        approved_docs=approved,
        approval_valid=all(doc_id in approved for doc_id in p.doc_ids(route.docs)),
        skipped=_is_skipped(route, p),
        dated=tuple(pair for pair in pairs if _dated(pair, facts.state)),
    )


def _dated(pair: DocSlot, state: SignaturesState) -> bool:
    """У размещения пары есть метки даты (14.3), включено оно или нет."""
    placement = state.placements.get(pair.doc_id, {}).get(pair.slot_id)
    return placement is not None and bool(placement.dates)


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


def approved_docs(route: SigningRoute, p: Participant, facts: RouteFacts) -> frozenset[str]:
    """Документы участника, которые он согласовал в этом раунде: отпечаток согласия совпал с источником (12.6).

    Картинка участника на документе открыта, только пока документ здесь; для хода шагов нужны все его документы.
    """
    approval = p.approval
    if approval is None or approval.round != route.round:
        return frozenset()
    return frozenset(
        doc_id for doc_id in p.doc_ids(route.docs) if approval.tokens.get(doc_id) == approval_token(facts.doc(doc_id))
    )


# --- остановка и статус -------------------------------------------------------------------------------------------

_STOP_PRIORITY = (StopReason.sent_changed, StopReason.frozen_changed, StopReason.marks_changed)


def _stop(route: SigningRoute, facts: RouteFacts) -> tuple[StopReason | None, UUID | None]:
    """Что останавливает маршрут: изменение документа (таблица 12.5) у идущего и завершённого, уход участника
    только у идущего: завершённому подписи уже поставлены.

    Документ сверяется со снимком по источнику подписи, то есть по версии на подписи: правка и пересборка меняют
    только рабочую сборку (`working_sha256`) и маршрут не останавливают. `rebuilt` расчёт больше не ставит."""
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
    # Версия на подписи подменена или удалена, документ убран из проекта (нет фактов): подписывать нечего.
    if seen is None or seen.compiled_sha256 != now.compiled_sha256:
        return StopReason.sent_changed
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
        if _is_skipped(route, p):
            continue  # пропущенному от проекта ничего не нужно
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
    """Участник сделал всё, что было возможно: до фиксации согласовал, после фиксации согласовал и подписал.

    Пропущенный автором прошёл шаг (13.3)."""
    if info.skipped:
        return True
    if not info.approved:
        return False
    return phase is RoutePhase.approval or info.early or not info.unsigned


def _view(
    route: SigningRoute, info: _Info, status: RouteStatus, progress: _Progress, facts: RouteFacts
) -> ParticipantView:
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
        approved=info.approval_valid,
        approved_docs=info.approved_docs,
        skip=_skip_option(route, info, state, progress, facts),
    )


def _state(route: SigningRoute, info: _Info, status: RouteStatus, progress: _Progress) -> ParticipantState:
    p = info.participant
    if status is RouteStatus.returned and route.stopped_by == p.id:
        return ParticipantState.returned
    if info.skipped:
        return ParticipantState.skipped
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
    ParticipantState.skipped: NextAction.done,
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


# --- пропуск (раздел 13) -------------------------------------------------------------------------------------------


def _unfinished(route: SigningRoute, pair: DocSlot, facts: RouteFacts) -> bool:
    """Пара ещё ждёт подписи: не подписана и не пропущена (на точке маршрута)."""
    status = slot_state(
        facts.state, pair.doc_id, pair.slot_id, facts.doc(pair.doc_id), profile_id=route.profile_id
    ).status
    return status not in (SlotStatus.signed, SlotStatus.skipped)


def _mark_drawn(pair: DocSlot, facts: RouteFacts) -> bool:
    """Метка слота сейчас рисуется на документе: размещение включено, картинка или плашка есть, слот не придержан
    и не пропущен (кроме `keep_mark`)."""
    state = facts.state
    placement = state.placements.get(pair.doc_id, {}).get(pair.slot_id)
    slot = state.slots.get(pair.slot_id)
    mark = mark_of(slot)
    if placement is None or not placement.enabled or mark is VisibleMark.none or state.mark_hidden(*pair):
        return False
    if mark is VisibleMark.png:
        return slot is not None and slot.png_path is not None and facts.doc(pair.doc_id).png_exists(slot.png_path)
    return True


def _signed_over_frozen(doc_id: str, facts: RouteFacts) -> bool:
    """Над зафиксированным PDF документа уже есть ЭП: перефиксация сбросила бы их (инвариант 3 раздела 2)."""
    if doc_id not in facts.state.frozen:
        return False
    return bool(facts.state.detached.get(doc_id) or facts.state.embedded.get(doc_id))


def _other_crypto(route: SigningRoute, p: Participant, doc_id: str, facts: RouteFacts) -> bool:
    """На документе есть ЭП-пара другого участника, которую не пропустили: документ маршрут зафиксирует."""
    for other in route.participants:
        if other.id == p.id:
            continue
        skipped = skipped_pairs(route, other)
        for pair in other.assignments:
            if pair.doc_id != doc_id or pair in skipped:
                continue
            slot = facts.state.slots.get(pair.slot_id)
            if method_of(slot.sign_mode if slot is not None else SignMode.image) in CRYPTO_METHODS:
                return True
    return False


def _skip_option(
    route: SigningRoute, info: _Info, state: ParticipantState, progress: _Progress, facts: RouteFacts
) -> SkipOption:
    """Можно ли пропустить участника: очередь дошла до него, а все оставшиеся подписи необязательны (13.3).

    Очередь это `to_approve`, `to_approve_sign`, `to_sign` или приглашённый на текущем шаге. Подписанные пары не
    пропускаются, остаются подписанными.
    """
    p = info.participant
    if state in (ParticipantState.done, ParticipantState.skipped):
        return SkipOption(False, SkipBlocker.done)
    in_queue = state in TURN_STATES or (state is ParticipantState.invited and p.step == progress.current_step)
    if route.status is not RouteStatus.active or not in_queue:
        return SkipOption(False, SkipBlocker.not_turn)
    if not p.assignments:
        return SkipOption(False, SkipBlocker.no_slots)
    remaining = tuple(pair for pair in p.assignments if _unfinished(route, pair, facts))
    if not remaining:
        return SkipOption(False, SkipBlocker.done)
    required = tuple(pair for pair in remaining if not facts.is_optional(pair))
    if required:
        return SkipOption(False, SkipBlocker.required_slots, pairs=remaining, required=required)
    drawn = tuple(dict.fromkeys(pair.doc_id for pair in remaining if _mark_drawn(pair, facts)))
    keeps = tuple(doc_id for doc_id in drawn if _signed_over_frozen(doc_id, facts))
    refreezes = tuple(
        doc_id
        for doc_id in drawn
        if doc_id not in keeps and doc_id in facts.state.frozen and _other_crypto(route, p, doc_id, facts)
    )
    return SkipOption(True, pairs=remaining, keeps_marks=keeps, refreezes=refreezes)


def _skip_effects(route: SigningRoute, facts: RouteFacts) -> list[Skip | Unskip]:
    """Разница между пропусками участников и `SignaturesState.skipped` (13.3): записать недостающее, убрать лишнее.

    Лишняя запись это пропуск пары маршрута, которого у участника уже нет (новый раунд снял его, пара стала
    обязательной). Чужие пары и записи не трогаются.
    """
    want: dict[DocSlot, tuple[int, bool]] = {}
    for p in route.participants:
        skip = p.skipped
        if skip is not None and skip.round == route.round:
            want.update({pair: (skip.round, pair.doc_id in skip.kept_marks) for pair in skip.pairs})
    effects: list[Skip | Unskip] = []
    for pair, (round_, keep) in want.items():
        record = facts.skip_record(pair)
        current = (record.route_id, record.profile_id, record.round, record.keep_mark) if record is not None else None
        if current != (str(route.id), route.profile_id, round_, keep):
            effects.append(Skip(pair.doc_id, pair.slot_id, keep))
    effects.extend(
        Unskip(pair.doc_id, pair.slot_id)
        for pair in dict.fromkeys(route.pairs)
        if pair not in want and facts.skip_record(pair) is not None
    )
    return effects


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
    files: list[Effect] = [
        *_skip_effects(route, facts),
        *_image_effects(infos, facts),
        *_signed_at_effects(infos, facts),
    ]
    if status is RouteStatus.active and progress.phase is RoutePhase.signing:
        files += _freeze_effects(route, facts, infos, files)
    return (*files, *_notices(route, infos, views, status, stop))


def _image_effects(infos: tuple[_Info, ...], facts: RouteFacts) -> list[Withhold | Release]:
    """Картинка участника на документе видна, только пока он согласовал версию на подписи этого документа
    (инвариант 2, раздел 12.6): на документе без изменений новая версия маршрута картинку не трогает."""
    effects: list[Withhold | Release] = []
    for info in infos:
        for pair in info.png:
            held = facts.is_withheld(pair)
            approved = pair.doc_id in info.approved_docs
            if approved and held:
                effects.append(Release(pair.doc_id, pair.slot_id, info.participant.id))
            elif not approved and not held:
                effects.append(Withhold(pair.doc_id, pair.slot_id))
    return effects


def _signed_at_effects(infos: tuple[_Info, ...], facts: RouteFacts) -> list[RecordSignedAt]:
    """Момент подписи пар с метками даты (14.4, 14.5): согласие участника, пока оно действует для документа.

    Пишется, когда даты согласия у размещения нет или её отпечаток другой (документ изменился и согласован заново).
    Новая версия с тем же отпечатком дату не меняет. Так же дозаполняется дата у того, кто согласовал до появления
    меток: она берётся из `Approval.at`.
    """
    effects: list[RecordSignedAt] = []
    for info in infos:
        approval = info.participant.approval
        if approval is None:
            continue
        for pair in info.dated:
            token = approval.tokens.get(pair.doc_id)
            if pair.doc_id not in info.approved_docs or token is None:
                continue
            current = facts.state.placements[pair.doc_id][pair.slot_id].signed_at
            if current is not None and current.source is SignedAtSource.approval and current.token == token:
                continue
            effects.append(RecordSignedAt(pair.doc_id, pair.slot_id, approval.at, token))
    return effects


def _date_redrawn(effect: RecordSignedAt, facts: RouteFacts) -> bool:
    """Запись даты меняет напечатанное: метки видны, а день по Москве другой (форматы зависят только от дня)."""
    state = facts.state
    if state.mark_hidden(effect.doc_id, effect.slot_id):
        return False
    current = state.placements[effect.doc_id][effect.slot_id].signed_at
    return current is None or display_day(current.at) != display_day(effect.at)


def _freeze_effects(
    route: SigningRoute, facts: RouteFacts, infos: tuple[_Info, ...], earlier: list[Effect]
) -> list[Effect]:
    """Видимый слой окончателен: заполнить плашки известными ключами и зафиксировать документы с ЭП (6.2)."""
    fills = _plate_fills(infos, facts)
    filled = {fill.slot_id for fill in fills}
    touched = {e.doc_id for e in earlier if isinstance(e, Withhold | Release)}
    # Дата согласия на метках даты (14.4) входит в видимый слой: документ с ней фиксируется заново (14.6).
    touched |= {e.doc_id for e in earlier if isinstance(e, RecordSignedAt) and _date_redrawn(e, facts)}
    # Пропуск убирает метку из видимого слоя: документ, где она уже рисуется, зафиксируют заново (13.5).
    touched |= {
        e.doc_id
        for e in earlier
        if isinstance(e, Skip) and not e.keep_mark and _mark_drawn(DocSlot(e.doc_id, e.slot_id), facts)
    }
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


def request_outcome(action: NextAction) -> RequestOutcome | None:
    """О чём просить участника с таким следующим действием (запрос и напоминание); None, если не о чем."""
    return _OUTCOMES.get(action)


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
