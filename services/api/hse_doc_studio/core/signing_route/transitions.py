"""Переходы маршрута подписания (docs/design/signing-route.md, разделы 5.3, 5.4 и 5.6).

Каждый переход берёт маршрут и возвращает новый, ничего не записывая. Сценарий под блокировкой строки маршрута
делает переход, считает `evaluate()`, выполняет эффекты, обновляет снимок (`refresh_snapshot`) и применяет расчёт
(`apply_evaluation`), затем сохраняет маршрут, события и уведомления одной транзакцией.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signing_route.engine import Evaluation, RouteFacts, evaluate
from hse_doc_studio.core.signing_route.entities import (
    SENDABLE_STATUSES,
    TURN_STATES,
    Approval,
    NextAction,
    Notified,
    Participant,
    RequestOutcome,
    RouteConflictError,
    RouteInputError,
    RoutePhase,
    RouteStatus,
    SigningRoute,
    StopReason,
)

_S = RouteStatus

# Переходы статусов (раздел 5.3). Сверх диаграммы: отменить можно и остановленный маршрут («в любой момент»,
# раздел 9); отменённый снимается с контроля, когда у точки появляется новый маршрут; завершённый снова идёт,
# если пропала подпись слота (таблица 5.5: ждёт только этот слот, маршрут не останавливается).
TRANSITIONS: dict[RouteStatus, frozenset[RouteStatus]] = {
    _S.draft: frozenset({_S.active, _S.cancelled}),
    _S.active: frozenset({_S.completed, _S.paused, _S.returned, _S.cancelled}),
    _S.paused: frozenset({_S.active, _S.cancelled}),
    _S.returned: frozenset({_S.active, _S.cancelled}),
    _S.completed: frozenset({_S.paused, _S.active, _S.archived}),
    _S.cancelled: frozenset({_S.active, _S.archived}),
    _S.archived: frozenset(),
}


def can_transition(source: RouteStatus, target: RouteStatus) -> bool:
    return target in TRANSITIONS[source]


def ensure_transition(source: RouteStatus, target: RouteStatus) -> None:
    if not can_transition(source, target):
        raise _invalid_transition(source, target)


def check_route(route: SigningRoute) -> None:
    """Маршрут собран верно: есть участники, шаги с 1, слот у одного участника, документы из маршрута."""
    if not route.participants:
        raise RouteInputError(
            "no_participants", localized_error("В маршруте нет участников", "The signing route has no participants")
        )
    if any(p.step < 1 for p in route.participants):
        raise RouteInputError("bad_step", localized_error("Шаги нумеруются с 1", "Steps are numbered from 1"))
    if len({p.id for p in route.participants}) != len(route.participants):
        raise RouteInputError(
            "duplicate_participant", localized_error("Участник указан дважды", "A participant is listed twice")
        )
    if len(set(route.pairs)) != len(route.pairs):
        raise RouteInputError(
            "duplicate_slot",
            localized_error("Слот документа назначен двум участникам", "A document slot is assigned twice"),
        )
    if any(pair.doc_id not in route.docs for pair in route.pairs):
        raise RouteInputError(
            "unknown_doc",
            localized_error("Слот назначен на документ вне маршрута", "A slot is assigned on a document outside"),
        )


def send(route: SigningRoute, facts: RouteFacts, *, by: UUID, at: datetime) -> SigningRoute:
    """«Отправить на подписание» и «Отправить заново» (разделы 5.4 и 5.6).

    Новый раунд, снимок отпечатков документов. Согласие участника переносится, если отпечатки всех его документов
    те же. Отправка это согласие отправителя, если он участник первого шага. Готовность его картинки и плашки,
    приглашённых и сборку документов сценарий проверяет по расчёту отправленного маршрута (`ParticipantView`).
    """
    if route.status not in SENDABLE_STATUSES:
        raise _invalid_transition(route.status, RouteStatus.active)
    check_route(route)
    round_ = route.round + 1
    first = route.steps[0]
    participants = tuple(
        _resend(p, facts.tokens(p.doc_ids(route.docs)), round_, sender=p.user_id == by and p.step == first, at=at)
        for p in route.participants
    )
    return replace(
        route,
        status=RouteStatus.active,
        phase=RoutePhase.approval,
        round=round_,
        participants=participants,
        snapshot=facts.snapshot(route.docs),
        sent_by=by,
        sent_at=at,
        completed_at=None,
        stop_reason=None,
        stopped_by=None,
    )


def _resend(p: Participant, tokens: dict[str, str], round_: int, *, sender: bool, at: datetime) -> Participant:
    approval = p.approval
    if sender:
        approval = Approval(round=round_, tokens=tokens, at=at)
    elif approval is not None and dict(approval.tokens) == tokens:
        approval = replace(approval, round=round_, phase=RoutePhase.approval)
    else:
        approval = None
    return replace(p, approval=approval, notified=None, reminded_at=None, reminders=0)


def approve(route: SigningRoute, facts: RouteFacts, participant_id: UUID, *, at: datetime) -> SigningRoute:
    """Записать согласие участника на текущие сборки его документов. Только в его очередь (инвариант 1).

    Картинка должна быть загружена, данные плашки известны: иначе согласие не сдвинуло бы маршрут.
    Отпечатки, которые видел человек (`expected`), сверяет сценарий до вызова. При «Согласовать и подписать»
    сценарий выполняет файловые эффекты расчёта (фиксацию), подписывает и только потом рассылает уведомления:
    иначе участник получил бы запрос «подпишите итоговый PDF» посреди своего же действия.
    """
    p = route.participant(participant_id)
    evaluation = evaluate(route, facts)
    view = evaluation.participant(participant_id)
    if evaluation.status is not RouteStatus.active or view.next_action not in (
        NextAction.approve,
        NextAction.approve_and_sign,
    ):
        raise _not_your_turn()
    if view.needs_image:
        raise RouteConflictError(
            "image_required", localized_error("Загрузите картинку подписи", "Upload the signature image")
        )
    if view.needs_plate:
        raise RouteConflictError(
            "plate_required",
            localized_error("Укажите ключ или сертификат для плашки", "Set the key or certificate for the plate"),
        )
    approval = Approval(
        round=route.round,
        tokens=facts.tokens(p.doc_ids(route.docs)),
        at=at,
        phase=evaluation.phase or RoutePhase.approval,
    )
    return route.with_participant(replace(p, approval=approval))


def return_route(route: SigningRoute, facts: RouteFacts, participant_id: UUID) -> SigningRoute:
    """«Вернуть на доработку»: любой участник в свою очередь (раздел 5.6). Комментарий хранит событие."""
    route.participant(participant_id)
    evaluation = evaluate(route, facts)
    if evaluation.status is not RouteStatus.active or evaluation.participant(participant_id).state not in TURN_STATES:
        raise _not_your_turn()
    return replace(
        route, status=RouteStatus.returned, phase=None, stop_reason=StopReason.returned, stopped_by=participant_id
    )


def cancel(route: SigningRoute) -> SigningRoute:
    """«Отменить маршрут». Поставленные ЭП и придержанные картинки остаются как есть (раздел 5.6)."""
    ensure_transition(route.status, RouteStatus.cancelled)
    return replace(route, status=RouteStatus.cancelled, phase=None, stop_reason=None, stopped_by=None)


def archive(route: SigningRoute) -> SigningRoute:
    """«Снять с контроля» или новый маршрут точки: маршрут больше не держит документы."""
    ensure_transition(route.status, RouteStatus.archived)
    return replace(route, status=RouteStatus.archived, phase=None)


def apply_evaluation(route: SigningRoute, evaluation: Evaluation, *, at: datetime) -> SigningRoute:
    """Статус и фаза по расчёту: остановка, завершение, возобновление завершённого."""
    status = evaluation.status
    if status is route.status:
        return route if evaluation.phase is route.phase else replace(route, phase=evaluation.phase)
    ensure_transition(route.status, status)
    if status is RouteStatus.paused:
        return replace(route, status=status, phase=None, stop_reason=evaluation.stop, stopped_by=evaluation.stopped_by)
    completed_at = at if status is RouteStatus.completed else None
    return replace(route, status=status, phase=evaluation.phase, completed_at=completed_at)


def refresh_snapshot(route: SigningRoute, facts: RouteFacts) -> SigningRoute:
    """Снимок после эффектов маршрута и действий подписанта на своей странице (картинка, плашка, способ, ЭП).

    Видимый слой и фиксация становятся текущими; сборка остаётся той, что отправлена: маршрут сам не
    пересобирает. Вызывается под `project_lock` сразу после записи файлов, иначе чужая правка между записью и
    снимком не будет замечена.
    """
    now = facts.snapshot(route.docs)
    snapshot = {
        doc_id: replace(now[doc_id], compiled_sha256=seen.compiled_sha256)
        if (seen := route.snapshot.get(doc_id)) is not None
        else now[doc_id]
        for doc_id in route.docs
    }
    return replace(route, snapshot=snapshot)


def mark_notified(route: SigningRoute, participant_id: UUID, outcome: RequestOutcome, *, at: datetime) -> SigningRoute:
    """Запомнить запрос участнику, чтобы расчёт не повторял его в этом раунде."""
    p = route.participant(participant_id)
    return route.with_participant(replace(p, notified=Notified(round=route.round, outcome=outcome, at=at)))


def _invalid_transition(source: RouteStatus, target: RouteStatus) -> RouteConflictError:
    return RouteConflictError(
        "invalid_transition",
        localized_error(
            f"Маршрут в состоянии «{source}» нельзя перевести в «{target}»",
            f"A signing route in “{source}” cannot become “{target}”",
        ),
    )


def _not_your_turn() -> RouteConflictError:
    return RouteConflictError(
        "not_your_turn", localized_error("Сейчас не ваша очередь по маршруту", "It is not your turn in the route")
    )
