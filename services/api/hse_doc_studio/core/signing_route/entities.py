"""Сущности маршрута подписания (docs/design/signing-route.md, разделы 5.1 и 5.3).

Маршрут хранит людей, порядок, согласия и события. Что подписано и чем, знает состояние подписей
(`SignaturesState`), маршрут это не дублирует (инвариант 5). Значения неизменяемые: переходы
(`transitions.py`) возвращают новый маршрут, расчёт (`engine.py`) только читает.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import NamedTuple
from uuid import UUID

from hse_doc_studio.core.i18n import localized_error

# Комментарий «Вернуть на доработку» обязателен и не длиннее этого (раздел 5.6).
RETURN_COMMENT_MAX = 2000


class RouteStatus(StrEnum):
    """Статус маршрута (раздел 5.3)."""

    draft = "draft"  # готовится, ещё не отправлен
    active = "active"  # идёт: согласования и подписи
    paused = "paused"  # остановлен: документ изменился или участник ушёл
    returned = "returned"  # подписант вернул на доработку
    completed = "completed"  # все согласовали и подписали; следит за документами
    cancelled = "cancelled"  # отменён автором
    archived = "archived"  # снят с контроля


# Незавершённые маршруты: на точку сдачи не больше одного (уникальный частичный индекс, раздел 5.8).
OPEN_STATUSES = frozenset({RouteStatus.draft, RouteStatus.active, RouteStatus.paused, RouteStatus.returned})
# Маршрут держит свои документы: документ не входит в два таких маршрута (`signing_route_docs.active`).
HOLDING_STATUSES = frozenset({RouteStatus.active, RouteStatus.paused, RouteStatus.returned, RouteStatus.completed})
# Маршрут сверяет документы со снимком и останавливается по таблице 5.5.
WATCHING_STATUSES = frozenset({RouteStatus.active, RouteStatus.completed})
# Где автор правит людей, порядок и слоты и откуда «Отправить заново» без изменений документов (раздел 5.6).
EDITABLE_STATUSES = frozenset({RouteStatus.draft, RouteStatus.paused, RouteStatus.returned, RouteStatus.cancelled})
# Откуда «Отправить новую версию» (раздел 12.6): только если у документа кандидат не равен версии на подписи
# (иначе 409 `nothing_changed`), с теми же людьми и порядком.
NEW_VERSION_STATUSES = frozenset({RouteStatus.active, RouteStatus.completed})
# Откуда можно отправить: первый раз, заново или новую версию (разделы 5.6 и 12.6).
SENDABLE_STATUSES = EDITABLE_STATUSES | NEW_VERSION_STATUSES


class RoutePhase(StrEnum):
    """Фаза идущего маршрута (раздел 4.2)."""

    approval = "approval"  # шаги 1..L: согласование по порядку, картинки встают при согласовании
    signing = "signing"  # видимый слой окончателен: документы зафиксированы, идут ЭП
    done = "done"  # все согласовали и все слоты маршрута `signed`


class StopReason(StrEnum):
    """Почему маршрут остановлен (разделы 5.4 и 12.5).

    `rebuilt` расчёт больше не ставит (12.5): значение остаётся для маршрутов, остановленных на 0.20.0, и истории
    событий.
    """

    rebuilt = "rebuilt"  # собранный PDF другой (0.20.0)
    sent_changed = "sent_changed"  # версия на подписи другая или удалена, документ убран из проекта
    frozen_changed = "frozen_changed"  # зафиксированный PDF другой или удалён вне маршрута
    marks_changed = "marks_changed"  # видимый слой другой, а маршрут его не менял
    participant_left = "participant_left"  # участник ушёл из проекта или сменил персону
    returned = "returned"  # подписант вернул на доработку


class ParticipantState(StrEnum):
    """Состояние участника: вычисляется расчётом, не хранится (раздел 5.3)."""

    invited = "invited"  # приглашение не принято; шаг ждёт его
    waiting = "waiting"  # его шаг ещё не настал или он ждёт фиксации
    to_approve = "to_approve"  # его очередь согласовать
    to_approve_sign = "to_approve_sign"  # его очередь, документы зафиксированы: согласовать и подписать
    to_sign = "to_sign"  # согласовал, документы зафиксированы, ждём его ЭП
    done = "done"  # согласовал, все его слоты `signed`
    returned = "returned"  # вернул на доработку (до следующей отправки)
    skipped = "skipped"  # пропущен автором: оставшиеся подписи необязательны (раздел 13)


# В этих состояниях участник может вернуть документ на доработку (раздел 5.6).
TURN_STATES = frozenset({ParticipantState.to_approve, ParticipantState.to_approve_sign, ParticipantState.to_sign})


class NextAction(StrEnum):
    """Что участнику сделать сейчас: кнопка на странице подписания (разделы 3.2 и 4.4)."""

    wait = "wait"
    approve = "approve"  # «Согласовать»
    approve_and_sign = "approve_and_sign"  # «Согласовать и подписать»
    sign = "sign"  # «Подписать» итоговый PDF
    done = "done"


class RequestOutcome(StrEnum):
    """Что просит запрос подписанту: `outcome` уведомления `signing_request` (раздел 6.6)."""

    approve = "approve"
    approve_sign = "approve_sign"
    sign = "sign"


class Notice(StrEnum):
    """Уведомления маршрута. Значения совпадают с видами `NotificationKind` из раздела 6.6."""

    request = "signing_request"
    reminder = "signing_reminder"
    returned = "signing_returned"
    paused = "signing_paused"
    completed = "signing_completed"
    cancelled = "signing_cancelled"
    # Новая версия (12.6): тем, кто согласовал или подписал изменившийся документ, но чья очередь ещё не настала.
    new_version = "signing_new_version"
    # Пропущенному участнику (13.7): его подпись не требуется. «Входящие» и письмо.
    skipped = "signing_skipped"


class EventKind(StrEnum):
    """Вид события маршрута (раздел 5.1)."""

    sent = "sent"
    approved = "approved"
    signed = "signed"
    returned = "returned"
    paused = "paused"
    resumed = "resumed"
    cancelled = "cancelled"
    completed = "completed"
    reminded = "reminded"
    invited = "invited"
    frozen = "frozen"
    skipped = "skipped"  # автор пропустил участника (раздел 13)


class SkipBlocker(StrEnum):
    """Почему участника нельзя пропустить (`skip.blocker`, `reason` ошибки `participant_not_skippable`, 13.6)."""

    not_turn = "not_turn"  # не его очередь
    required_slots = "required_slots"  # среди оставшихся подписей есть обязательные
    no_slots = "no_slots"  # согласующий без подписей: нечего отмечать необязательным
    done = "done"  # уже закончил или пропущен


class RouteInputError(ValueError):
    """Маршрут собран неверно: нет участников, шаг меньше 1, слот у двух участников (ответ 400)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RouteConflictError(Exception):
    """Действие несовместимо с состоянием маршрута (ответ 409, `not_participant` это 404).

    Коды: `invalid_transition`, `not_participant`, `not_your_turn`, `image_required`, `plate_required`,
    `route_locked`, `nothing_changed`, `participant_not_skippable`, `date_from_route`.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ParticipantNotSkippableError(RouteConflictError):
    """Пропуск участника нельзя (409 `participant_not_skippable`, раздел 13.6): `reason`, а при `required_slots`
    ещё `slots`, обязательные пары, которые мешают."""

    def __init__(self, reason: SkipBlocker, slots: tuple[DocSlot, ...] = ()) -> None:
        super().__init__(
            "participant_not_skippable",
            localized_error("Этого участника нельзя пропустить", "This participant cannot be skipped"),
        )
        self.reason = reason
        self.slots = slots


def not_your_turn() -> RouteConflictError:
    """Действие участника не в его очередь, в том числе у маршрута, который не идёт (409 `not_your_turn`)."""
    return RouteConflictError(
        "not_your_turn", localized_error("Сейчас не ваша очередь по маршруту", "It is not your turn in the route")
    )


def route_locked() -> RouteConflictError:
    """Правка подписей документа идущего маршрута мимо маршрута (409 `route_locked`, раздел 5.5)."""
    return RouteConflictError(
        "route_locked",
        localized_error(
            "Документ на подписании: отмените маршрут, чтобы изменить подписи",
            "The document is out for signing: cancel the signing route to change its signatures",
        ),
    )


def date_from_route() -> RouteConflictError:
    """Ручная дата подписи на паре участника маршрута (409 `date_from_route`, signing-route.md, 14.6): дату даёт его
    согласие."""
    return RouteConflictError(
        "date_from_route",
        localized_error(
            "Дату этой подписи даёт согласование по маршруту: указать её вручную нельзя",
            "The date of this signature comes from the approval in the signing route: it cannot be set by hand",
        ),
    )


def route_holds_doc() -> RouteConflictError:
    """«Подписывать текущую сборку» у документа, который держит маршрут (409 `route_locked`, раздел 12.4)."""
    return RouteConflictError(
        "route_locked",
        localized_error(
            "Документ держит маршрут подписания: отмените маршрут или снимите его с контроля, чтобы подписывать "
            "текущую сборку",
            "A signing route holds the document: cancel the route or stop tracking it to sign the current build",
        ),
    )


def nothing_changed() -> RouteConflictError:
    """«Отправить новую версию» у идущего или завершённого маршрута без изменений (409 `nothing_changed`, 12.6)."""
    return RouteConflictError(
        "nothing_changed",
        localized_error(
            "Документы не менялись после отправки на подпись: новую версию отправлять нечего",
            "The documents have not changed since they were sent for signing: there is no new version to send",
        ),
    )


class DocSlot(NamedTuple):
    """Пара «документ, слот»: где стоит подпись участника."""

    doc_id: str
    slot_id: str


@dataclass(frozen=True)
class DocSnapshot:
    """Отпечатки документа, которые маршрут видел последними (разделы 5.5 и 12.5).

    `compiled_sha256` sha256 версии на подписи (источника подписи, `DocFacts.compiled_sha256`), снятой отправкой:
    маршрут сам её не меняет до следующей отправки, поэтому иное значение это подмена мимо маршрута
    (`sent_changed`). `marks_digest` и `frozen_sha256` маршрут меняет сам (открывает картинки, фиксирует) и
    обновляет снимок после своих эффектов (`transitions.refresh_snapshot`); иное отличие это изменение вне маршрута.

    `sent_at` когда отправлена эта версия документа (12.6): у документа без изменений новая версия маршрута его не
    трогает. None у маршрутов 0.20.0, тогда берётся `SigningRoute.sent_at` (`SigningRoute.doc_sent_at`). Это не
    отпечаток: в сравнении снимков не участвует.

    `replaced` эта версия заменила прежнюю версию на подписи (документ изменился, «Отправить новую версию»), а не
    отправлена впервые. Вместе с `sent_at` это говорит, какие документы изменил текущий раунд
    (`SigningRoute.round_changed_docs`). Тоже не отпечаток.
    """

    compiled_sha256: str | None
    marks_digest: str
    frozen_sha256: str | None = None
    sent_at: datetime | None = field(default=None, compare=False)
    replaced: bool = field(default=False, compare=False)


@dataclass(frozen=True)
class Approval:
    """Согласие участника: какую версию документов он согласовал.

    `tokens` отпечаток версии на подписи каждого его документа (`build:<sha>`, `engine.approval_token`). Согласие
    действует по каждому документу отдельно (12.6): документ согласован, пока его отпечаток совпадает; участник
    согласовал (для хода шагов), только если совпали отпечатки всех его документов. Отправка переносит согласие
    в новый раунд всегда, с прежними отпечатками. `phase` фаза маршрута в момент согласия: согласившие до
    фиксации (`approval`) подписывают ЭП после неё параллельно и не задерживают следующие шаги (раздел 4.2).
    """

    round: int
    tokens: Mapping[str, str]
    at: datetime
    phase: RoutePhase = RoutePhase.approval


@dataclass(frozen=True)
class Notified:
    """Последний запрос участнику: в каком раунде и о чём. Повторно о том же не уведомляем."""

    round: int
    outcome: RequestOutcome
    at: datetime


@dataclass(frozen=True)
class ParticipantSkip:
    """Пропуск участника автором (13.3): источник истины расчёта, а `SignaturesState.skipped` его эффект.

    `pairs` пары «документ, слот», которые остались неподписанными и пропущены (подписанные остаются подписанными).
    `kept_marks` документы, где метка осталась в зафиксированном PDF с ЭП (`keep_mark`, 13.5); `refrozen` документы,
    которые маршрут зафиксирует заново без метки. `by` кто пропустил. Раунд переносится отправкой, пока все
    `pairs` остаются необязательными (`transitions.send`).
    """

    round: int
    at: datetime
    by: UUID
    pairs: tuple[DocSlot, ...]
    kept_marks: tuple[str, ...] = ()
    refrozen: tuple[str, ...] = ()


@dataclass(frozen=True)
class Participant:
    """Участник маршрута: человек с персоной на своём шаге.

    `user_id` пусто, пока приглашение не принято. `invitation_id` id приглашения в проект (`inv_…`, как у
    `ProjectInvitation.id`). `assignments` его пары «документ, слот»; пусто у согласующего без подписи. Способ
    подписи берётся из слота (`SignatureSlot.sign_mode`), маршрут его не хранит.
    """

    id: UUID
    step: int
    persona: str
    user_id: UUID | None = None
    invitation_id: str | None = None
    assignments: tuple[DocSlot, ...] = ()
    approval: Approval | None = None
    notified: Notified | None = None
    reminded_at: datetime | None = None
    reminders: int = 0
    skipped: ParticipantSkip | None = None

    def doc_ids(self, route_docs: tuple[str, ...]) -> tuple[str, ...]:
        """Документы участника: где его слоты, а у согласующего без слотов все документы маршрута."""
        if not self.assignments:
            return route_docs
        return tuple(dict.fromkeys(pair.doc_id for pair in self.assignments))


@dataclass(frozen=True)
class SigningRoute:
    """Маршрут подписания точки сдачи (раздел 5.1).

    `participants` в порядке редактора; шаги это их номера `step`, внутри шага параллельно. `phase` задан только
    у идущего (`active`) и завершённого (`completed`) маршрута. `stopped_by` участник, чей возврат или уход
    остановил маршрут.

    `version` номер записи в хранилище: 0 у ещё не сохранённого, каждое сохранение его увеличивает. Хранилище
    принимает маршрут, только если с момента чтения его никто не перезаписал (`ISigningRouteRepository.save`),
    поэтому одновременные действия подписантов не затирают друг друга. Переходы его не трогают.

    `created_at` и `updated_at` время записи в хранилище (None у ещё не сохранённого): их ставит хранилище, в
    сравнении маршрутов они не участвуют.
    """

    id: UUID
    project_id: UUID
    profile_id: str
    created_by: UUID
    status: RouteStatus = RouteStatus.draft
    phase: RoutePhase | None = None
    round: int = 0
    docs: tuple[str, ...] = ()
    participants: tuple[Participant, ...] = ()
    snapshot: Mapping[str, DocSnapshot] = field(default_factory=dict)
    deadline: datetime | None = None
    message: str | None = None
    sent_by: UUID | None = None
    sent_at: datetime | None = None
    completed_at: datetime | None = None
    stop_reason: StopReason | None = None
    stopped_by: UUID | None = None
    version: int = 0
    created_at: datetime | None = field(default=None, compare=False)
    updated_at: datetime | None = field(default=None, compare=False)

    @property
    def steps(self) -> tuple[int, ...]:
        """Номера шагов по возрастанию, без повторов."""
        return tuple(sorted({p.step for p in self.participants}))

    @property
    def pairs(self) -> tuple[DocSlot, ...]:
        """Все пары «документ, слот» маршрута."""
        return tuple(pair for p in self.participants for pair in p.assignments)

    def doc_sent_at(self, doc_id: str) -> datetime | None:
        """Когда отправлена версия документа, которую подписывают (12.6); у маршрута 0.20.0 время отправки."""
        seen = self.snapshot.get(doc_id)
        if seen is not None and seen.sent_at is not None:
            return seen.sent_at
        return self.sent_at

    @property
    def round_changed_docs(self) -> tuple[str, ...]:
        """Документы, у которых текущий раунд отправил новую версию взамен прежней (12.6), в порядке маршрута.

        Пусто у первой отправки, после отмены (версия снята, документы отправлены заново) и у маршрута без новой
        версии. Раунд это определяет по снимку: время отправки документа равно времени отправки маршрута.
        """
        if self.sent_at is None:
            return ()
        return tuple(
            doc_id
            for doc_id in self.docs
            if (seen := self.snapshot.get(doc_id)) is not None and seen.replaced and seen.sent_at == self.sent_at
        )

    def participant(self, participant_id: UUID) -> Participant:
        for p in self.participants:
            if p.id == participant_id:
                return p
        raise RouteConflictError(
            "not_participant", localized_error("Вы не участник этого маршрута", "You are not in this signing route")
        )

    def participants_of(self, user_id: UUID) -> tuple[Participant, ...]:
        """Участники, которые этот пользователь (обычно один)."""
        return tuple(p for p in self.participants if p.user_id == user_id)

    def with_participant(self, participant: Participant) -> SigningRoute:
        """Маршрут с заменённым участником (по `id`)."""
        self.participant(participant.id)
        return replace(
            self, participants=tuple(participant if p.id == participant.id else p for p in self.participants)
        )


@dataclass(frozen=True)
class RouteEvent:
    """Событие маршрута: история для страницы подписания и автора (раздел 5.1).

    Комментарий возврата хранится здесь (`details["comment"]`), а не в аудите. `id` номер записи в хранилище
    (None у ещё не сохранённого), в сравнении событий не участвует.
    """

    route_id: UUID
    round: int
    at: datetime
    kind: EventKind
    actor_id: UUID | None = None
    participant_id: UUID | None = None
    details: Mapping[str, object] = field(default_factory=dict)
    id: int | None = field(default=None, compare=False)
