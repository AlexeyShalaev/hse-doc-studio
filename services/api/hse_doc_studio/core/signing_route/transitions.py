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
    NEW_VERSION_STATUSES,
    SENDABLE_STATUSES,
    TURN_STATES,
    Approval,
    DocSnapshot,
    NextAction,
    Notified,
    Participant,
    ParticipantNotSkippableError,
    ParticipantSkip,
    RequestOutcome,
    RouteConflictError,
    RouteInputError,
    RoutePhase,
    RouteStatus,
    SigningRoute,
    SkipBlocker,
    StopReason,
    not_your_turn,
    nothing_changed,
)
from hse_doc_studio.core.signing_route.versions import DocChange, has_news, still_optional, version_changes

_S = RouteStatus

# Переходы статусов (раздел 5.3). Сверх диаграммы: отменить можно и остановленный маршрут («в любой момент»,
# раздел 9); отменённый снимается с контроля, когда у точки появляется новый маршрут; завершённый снова идёт,
# если пропала подпись слота (таблица 5.5: ждёт только этот слот, маршрут не останавливается). «Отправить новую
# версию» (12.6): идущий остаётся идущим с новым раундом, завершённый снова идёт.
TRANSITIONS: dict[RouteStatus, frozenset[RouteStatus]] = {
    _S.draft: frozenset({_S.active, _S.cancelled}),
    _S.active: frozenset({_S.active, _S.completed, _S.paused, _S.returned, _S.cancelled}),
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


def send(route: SigningRoute, candidate: RouteFacts, *, by: UUID, at: datetime) -> SigningRoute:
    """«Отправить на подписание», «Отправить заново» и «Отправить новую версию» (разделы 5.4, 5.6 и 12.6).

    `candidate` факты кандидата (`RouteFacts.candidate()`): источник каждого документа это его текущая сборка, а
    у несобранного прежняя версия на подписи. Новый раунд, снимок по кандидату: сценарий после перехода снимает
    версию на подписи у документов `version_changes(route, candidate).to_pin`, и факты сверки совпадают со
    снимком. У документа без изменений снимок сохраняет время его отправки (`DocSnapshot.sent_at`), у
    изменившегося и нового это `at`.

    Из `active` и `completed` только новая версия: без изменений 409 `nothing_changed`. Люди и порядок те же.

    Пропуск участника (13.3) переносится в новый раунд, пока все пропущенные пары остаются необязательными; без
    изменений документов отправка из `active` и `completed` допустима, если кого-то это вернёт в маршрут.

    Согласие каждого участника переносится в новый раунд всегда, с прежними отпечатками (12.6): оно действует по
    документам, поэтому на документах без изменений картинки, B и ЭП остаются, а изменившиеся документы участник
    согласует заново в свою очередь. Отправка это согласие отправителя, если он участник первого шага. Готовность
    его картинки и плашки, приглашённых и сборку документов сценарий проверяет по расчёту отправленного маршрута
    на кандидате (`ParticipantView`).
    """
    if route.status not in SENDABLE_STATUSES:
        raise _invalid_transition(route.status, RouteStatus.active)
    check_route(route)
    changes = version_changes(route, candidate)
    if route.status in NEW_VERSION_STATUSES and not has_news(route, candidate):
        raise nothing_changed()
    round_ = route.round + 1
    first = route.steps[0]
    participants = tuple(
        _resend(
            p,
            candidate.tokens(p.doc_ids(route.docs)),
            round_,
            sender=p.user_id == by and p.step == first,
            at=at,
            keep_skip=still_optional(p, candidate),
        )
        for p in route.participants
    )
    now = candidate.snapshot(route.docs)
    snapshot = {doc_id: _sent_snapshot(route, doc_id, now[doc_id], changes.docs[doc_id], at) for doc_id in route.docs}
    return replace(
        route,
        status=RouteStatus.active,
        phase=RoutePhase.approval,
        round=round_,
        participants=participants,
        snapshot=snapshot,
        sent_by=by,
        sent_at=at,
        completed_at=None,
        stop_reason=None,
        stopped_by=None,
    )


def _sent_snapshot(route: SigningRoute, doc_id: str, now: DocSnapshot, change: DocChange, at: datetime) -> DocSnapshot:
    """Снимок документа после отправки (12.6): у документа без изменений время его версии и пометка `replaced`
    прежние, у изменившегося `at` и `replaced`, у нового (первая отправка, после отмены) `at`."""
    if change is DocChange.same:
        seen = route.snapshot.get(doc_id)
        return replace(now, sent_at=route.doc_sent_at(doc_id), replaced=seen.replaced if seen is not None else False)
    return replace(now, sent_at=at, replaced=change is DocChange.changed)


def _resend(  # noqa: PLR0913 — что меняет раунд у одного участника
    p: Participant, tokens: dict[str, str], round_: int, *, sender: bool, at: datetime, keep_skip: bool
) -> Participant:
    # Пропуск переносится, пока все пропущенные пары необязательны (13.3); иначе участник вернётся: расчёт уберёт
    # запись `skipped` (`Unskip`), и он получит запрос в свою очередь.
    skipped = replace(p.skipped, round=round_) if p.skipped is not None and keep_skip else None
    approval = p.approval
    if sender:
        approval = Approval(round=round_, tokens=tokens, at=at)
    elif approval is not None:
        # Переносится всегда: что из него ещё действует, решают отпечатки по документам (`engine.approved_docs`).
        approval = replace(approval, round=round_, phase=RoutePhase.approval)
    return replace(p, approval=approval, notified=None, reminded_at=None, reminders=0, skipped=skipped)


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
        raise not_your_turn()
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


def skip(route: SigningRoute, facts: RouteFacts, participant_id: UUID, *, by: UUID, at: datetime) -> SigningRoute:
    """«Пропустить» участника (раздел 13.3): очередь дошла до него, а все оставшиеся подписи необязательны.

    Пропущенными становятся оставшиеся неподписанные пары; подписанные остаются подписанными. Что станет с метками
    пропущенных (`kept_marks`, `refrozen`), считает расчёт по тем же фактам: сценарий выполняет затем эффекты
    `Skip` и фиксацию. Отказ: 409 `invalid_transition` у маршрута не в `active`, `participant_not_skippable` с
    причиной (`SkipBlocker`) иначе.
    """
    if route.status is not RouteStatus.active:
        raise RouteConflictError(
            "invalid_transition",
            localized_error(
                f"Пропустить участника можно только у идущего маршрута, а он в состоянии «{route.status}»",
                f"A participant can only be skipped in a running route, but it is “{route.status}”",
            ),
        )
    p = route.participant(participant_id)
    option = evaluate(route, facts).participant(participant_id).skip
    if not option.available:
        raise ParticipantNotSkippableError(option.blocker or SkipBlocker.not_turn, option.required)
    skipped = ParticipantSkip(
        round=route.round, at=at, by=by, pairs=option.pairs, kept_marks=option.keeps_marks, refrozen=option.refreezes
    )
    return route.with_participant(replace(p, skipped=skipped))


def return_route(route: SigningRoute, facts: RouteFacts, participant_id: UUID) -> SigningRoute:
    """«Вернуть на доработку»: любой участник в свою очередь (раздел 5.6). Комментарий хранит событие."""
    route.participant(participant_id)
    evaluation = evaluate(route, facts)
    if evaluation.status is not RouteStatus.active or evaluation.participant(participant_id).state not in TURN_STATES:
        raise not_your_turn()
    return replace(
        route, status=RouteStatus.returned, phase=None, stop_reason=StopReason.returned, stopped_by=participant_id
    )


def cancel(route: SigningRoute) -> SigningRoute:
    """«Отменить маршрут». Поставленные ЭП и придержанные картинки остаются как есть (раздел 5.6).

    Отмена снимает версии на подписи (12.4), поэтому снимок отправленных версий пуст: следующая отправка снимает
    документы заново (`DocChange.new`). Согласия участников с их отпечатками остаются и переносятся, как всегда.
    """
    ensure_transition(route.status, RouteStatus.cancelled)
    return replace(route, status=RouteStatus.cancelled, phase=None, stop_reason=None, stopped_by=None, snapshot={})


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

    Видимый слой и фиксация становятся текущими; версия на подписи и время её отправки остаются теми, что
    отправлены: маршрут сам их не меняет до следующей отправки. Вызывается под `project_lock` сразу после записи
    файлов, иначе чужая правка между записью и снимком не будет замечена.
    """
    now = facts.snapshot(route.docs)
    snapshot: dict[str, DocSnapshot] = {
        doc_id: replace(seen, marks_digest=now[doc_id].marks_digest, frozen_sha256=now[doc_id].frozen_sha256)
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
