"""Действия подписанта на своей странице (docs/design/signing-route.md, разделы 4.2, 6.3, 7 и 8.1).

Чистые правила сценариев `task`: чья очередь, какие отпечатки человек должен вернуть (`expected`), какой способ
подписи он может выбрать сейчас и как его выбор, картинка и данные плашки ложатся в состояние подписей. Файлы и
базу пишут сценарии (`use_cases/signing_route/signer.py`), здесь только расчёт.

Очередь:

- согласовать: `next_action` это `approve` или `approve_and_sign`;
- подписать итоговый PDF: `sign`;
- вернуть на доработку: состояние из `TURN_STATES` (проверяет `transitions.return_route`);
- картинка, данные плашки и смена способа: только пока видимый слой ещё не окончателен, то есть в состоянии
  `to_approve`. После фиксации (`to_approve_sign`) такая правка изменила бы зафиксированный PDF и сбросила чужие
  ЭП (инвариант 3), поэтому она отклоняется.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace
from uuid import UUID

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signatures.plan import (
    CRYPTO_METHODS,
    DocFacts,
    SignMethod,
    SlotStatus,
    VisibleMark,
    frozen_is_current,
    mark_of,
    method_of,
    slot_state,
)
from hse_doc_studio.core.signing_route.engine import Evaluation, ParticipantView, RouteFacts, approval_token
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    NextAction,
    Participant,
    ParticipantState,
    RouteConflictError,
    RouteInputError,
    RouteStatus,
    SigningRoute,
    not_your_turn,
)
from hse_doc_studio.core.signing_route.readiness import DocChangedError
from hse_doc_studio.core.value_objects import FrozenPdf, SignatureSlot, SignaturesState, SignerInfo

APPROVE_ACTIONS = frozenset({NextAction.approve, NextAction.approve_and_sign})
SIGN_ACTIONS = frozenset({NextAction.sign})

# Способ, который подписант выбирает на своей странице, и режим слота, в который он превращается, если слот сейчас
# подписывается иначе: картинка, плашка открепленной ЭП, PAdES без видимой метки.
_MODES = {
    SignMethod.image: SignMode.image,
    SignMethod.detached: SignMode.detached_text,
    SignMethod.pades: SignMode.crypto_invisible,
}


class VisibleLayerFinalError(RouteConflictError):
    """Документы уже зафиксированы: картинку, способ и данные плашки менять нельзя (409 `visible_layer_final`)."""

    def __init__(self) -> None:
        super().__init__(
            "visible_layer_final",
            localized_error(
                "Документы уже зафиксированы: картинку, способ подписи и данные плашки изменить нельзя",
                "The documents are already frozen: the image, the signing method and the plate cannot be changed",
            ),
        )


class MethodNotAllowedError(RouteConflictError):
    """Способ подписи сейчас выбрать нельзя: его не принимает точка или он изменил бы зафиксированный PDF (409)."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            "method_not_allowed",
            message
            or localized_error(
                "Этот способ подписи сейчас выбрать нельзя", "This signing method cannot be chosen right now"
            ),
        )


class InvalidFileError(RouteInputError):
    """Загруженный файл не подходит: не PNG, слишком большой, не сертификат или в нём закрытый ключ (400)."""

    def __init__(self, message: str) -> None:
        super().__init__("invalid_file", message)


def acting_participant(route: SigningRoute, evaluation: Evaluation, user_id: UUID) -> Participant:
    """Участник, которым этот человек действует в маршруте; не участнику `not_participant` (ответ 404).

    Обычно участник один. Если человек стоит в маршруте дважды (две персоны), берётся тот, от кого сейчас ждут
    действия, иначе первый по порядку.
    """
    mine = tuple(p for p in route.participants if p.user_id is not None and p.user_id == user_id)
    if not mine:
        raise RouteConflictError(
            "not_participant", localized_error("Вы не участник этого маршрута", "You are not in this signing route")
        )
    waited = (NextAction.approve, NextAction.approve_and_sign, NextAction.sign)
    return next((p for p in mine if evaluation.participant(p.id).next_action in waited), mine[0])


def ensure_turn(evaluation: Evaluation, view: ParticipantView, actions: Collection[NextAction]) -> None:
    """Маршрут идёт и от участника сейчас ждут одно из `actions`; иначе `not_your_turn`."""
    if evaluation.status is not RouteStatus.active or view.next_action not in actions:
        raise not_your_turn()


def ensure_layer_open(evaluation: Evaluation, view: ParticipantView, p: Participant) -> None:
    """Участник вправе менять свою картинку и данные плашки: его очередь согласовать, фиксации ещё не было."""
    if evaluation.status is RouteStatus.active and view.state is ParticipantState.to_approve_sign:
        raise VisibleLayerFinalError
    if evaluation.status is not RouteStatus.active or view.state is not ParticipantState.to_approve:
        raise not_your_turn()
    if not p.assignments:
        # Согласующему без слотов нечего ставить на документ.
        raise not_your_turn()


# --- отпечатки ------------------------------------------------------------------------------------------------------


def doc_token(action: NextAction, doc: DocFacts, frozen: FrozenPdf | None) -> str | None:
    """Отпечаток документа, который человек возвращает в `expected` своего следующего действия (раздел 8.1).

    - `approve`: сборка, `build:<sha>`;
    - `approve_and_sign` до фиксации: сборка и видимый слой, `build:<sha>:<слой>` (сервер зафиксирует сам);
    - `approve_and_sign` и `sign` у зафиксированного документа: байты фиксации, `pdf:<sha>`. Это отпечаток B, а не
      файла со встроенными подписями: после фиксации подписанты подписывают параллельно, и чужая PAdES, дописанная
      к тому же B, не должна отменять уже открытую страницу;
    - `sign` у документа без фиксации (на нём нет ЭП): сборка;
    - ждать или готово: None.
    """
    if action in (NextAction.wait, NextAction.done):
        return None
    if action is NextAction.approve:
        return approval_token(doc)
    if frozen is not None and frozen_is_current(frozen, doc) is None:
        return f"pdf:{frozen.sha256}"
    if action is NextAction.approve_and_sign:
        return f"{approval_token(doc)}:{doc.marks_digest}"
    return approval_token(doc)


def task_tokens(route: SigningRoute, p: Participant, action: NextAction, facts: RouteFacts) -> dict[str, str | None]:
    """Отпечатки документов участника для его следующего действия."""
    return {
        doc_id: doc_token(action, facts.doc(doc_id), facts.state.frozen.get(doc_id)) for doc_id in p.doc_ids(route.docs)
    }


def check_expected(tokens: Mapping[str, str | None], expected: Mapping[str, str]) -> None:
    """Человек видел то, что есть сейчас; иначе `doc_changed` с документами, которые разошлись."""
    changed = [doc_id for doc_id, token in tokens.items() if expected.get(doc_id) != token]
    if changed:
        raise DocChangedError(changed)


def changed_docs(route: SigningRoute, facts: RouteFacts) -> tuple[str, ...]:
    """Документы, которые разошлись со снимком маршрута (изменились вне маршрута, таблица 5.5)."""
    now = facts.snapshot(route.docs)
    return tuple(doc_id for doc_id in route.docs if route.snapshot.get(doc_id) != now[doc_id])


# --- слоты участника ------------------------------------------------------------------------------------------------


def own_slots(p: Participant) -> tuple[str, ...]:
    """Слоты участника без повторов: состояние слота общее для всех документов проекта."""
    return tuple(dict.fromkeys(pair.slot_id for pair in p.assignments))


def _mode(state: SignaturesState, slot_id: str) -> SignMode:
    slot = state.slots.get(slot_id)
    return slot.sign_mode if slot is not None else SignMode.image


def current_method(p: Participant, state: SignaturesState) -> SignMethod | None:
    """Способ слотов участника (первого слота); None у согласующего без слотов."""
    slots = own_slots(p)
    return method_of(_mode(state, slots[0])) if slots else None


def unsigned_crypto(p: Participant, facts: RouteFacts) -> tuple[DocSlot, ...]:
    """Пары участника с ЭП, которые ещё не подписаны."""
    pairs: list[DocSlot] = []
    for pair in p.assignments:
        if method_of(_mode(facts.state, pair.slot_id)) not in CRYPTO_METHODS:
            continue
        if slot_state(facts.state, pair.doc_id, pair.slot_id, facts.doc(pair.doc_id)).status is not SlotStatus.signed:
            pairs.append(pair)
    return tuple(pairs)


def image_ready(p: Participant, facts: RouteFacts) -> bool:
    """У каждого слота участника есть загруженная картинка (каким бы способом слот сейчас ни подписывался)."""
    if not p.assignments:
        return False
    for pair in p.assignments:
        slot = facts.state.slots.get(pair.slot_id)
        if slot is None or slot.png_path is None or not facts.doc(pair.doc_id).png_exists(slot.png_path):
            return False
    return True


def known_plate(p: Participant, facts: RouteFacts) -> SignerInfo | None:
    """Данные плашки участника: записанные в его слот, иначе известные о нём (профиль подписанта, 6.5)."""
    for slot_id in own_slots(p):
        slot = facts.state.slots.get(slot_id)
        if slot is not None and slot.signer is not None:
            return slot.signer
    return facts.plates.get(p.user_id) if p.user_id is not None else None


def plates_without_signer(p: Participant, state: SignaturesState) -> tuple[str, ...]:
    """Слоты участника с плашкой, в которую ещё не записан подписант."""
    return tuple(
        slot_id
        for slot_id in own_slots(p)
        if mark_of(state.slots.get(slot_id)) is VisibleMark.plate
        and ((slot := state.slots.get(slot_id)) is None or slot.signer is None)
    )


# --- способ ---------------------------------------------------------------------------------------------------------


def available_methods(
    p: Participant,
    view: ParticipantView,
    state: SignaturesState,
    point_methods: Sequence[str],
    *,
    server_keys: bool = True,
) -> tuple[SignMethod, ...]:
    """Способы, которые участник может выбрать сейчас (раздел 6.3).

    `point_methods` способы, которые точка разрешает его слотам. Выбирать можно только на своём шаге до фиксации
    (`to_approve`): после неё любой другой способ изменил бы видимый слой, остаётся текущий. PAdES ставит только
    ключ Студии на сервере, поэтому при запрете серверных ключей (`server_keys`) его не предлагаем.
    """
    current = current_method(p, state)
    if current is None:
        return ()
    if view.state is not ParticipantState.to_approve:
        return (current,)
    allowed = [SignMethod(m) for m in point_methods]
    return tuple(m for m in allowed if server_keys or m is not SignMethod.pades or m is current)


def mode_for(method: SignMethod, current: SignMode) -> SignMode:
    """Режим слота для выбранного способа; слот, который уже подписывается этим способом, не меняется."""
    return current if method_of(current) is method else _MODES[method]


def with_method(state: SignaturesState, p: Participant, method: SignMethod) -> SignaturesState:
    """Состояние подписей, где слоты участника подписываются способом `method`.

    Слот, у которого больше нет картинки на странице, снимается с придержания: придерживаются только картинки
    (раздел 6.1), а придержанную плашку расчёт уже не открыл бы.
    """
    slots = dict(state.slots)
    for slot_id in own_slots(p):
        slot = slots.get(slot_id) or SignatureSlot(None, None, None)
        mode = mode_for(method, slot.sign_mode)
        if mode is not slot.sign_mode:
            slots[slot_id] = replace(
                slot, sign_mode=mode, sign_reason=slot.sign_reason if method in CRYPTO_METHODS else ""
            )
    changed = replace(state, slots=slots)
    withheld = {
        doc_id: frozenset(
            slot_id
            for slot_id in held
            if DocSlot(doc_id, slot_id) not in p.assignments or mark_of(slots.get(slot_id)) is VisibleMark.png
        )
        for doc_id, held in state.withheld.items()
    }
    return replace(changed, withheld={doc_id: held for doc_id, held in withheld.items() if held})


def with_signer(state: SignaturesState, slot_ids: Sequence[str], signer: SignerInfo) -> SignaturesState:
    """Состояние подписей, где на плашках слотов `slot_ids` указан подписант `signer`.

    Уровень подписи, выбранный раньше, сохраняется, если новый подписант его не задаёт (как при обычной настройке
    плашки слота).
    """
    slots = dict(state.slots)
    for slot_id in slot_ids:
        slot = slots.get(slot_id) or SignatureSlot(None, None, None)
        new = signer
        if slot.signer is not None and not signer.level:
            new = replace(signer, level=slot.signer.level)
        slots[slot_id] = replace(slot, signer=new)
    return replace(state, slots=slots)
