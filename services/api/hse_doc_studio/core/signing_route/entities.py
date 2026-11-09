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
# Откуда можно отправить (первый раз или заново, раздел 5.6).
SENDABLE_STATUSES = frozenset({RouteStatus.draft, RouteStatus.paused, RouteStatus.returned, RouteStatus.cancelled})


class RoutePhase(StrEnum):
    """Фаза идущего маршрута (раздел 4.2)."""

    approval = "approval"  # шаги 1..L: согласование по порядку, картинки встают при согласовании
    signing = "signing"  # видимый слой окончателен: документы зафиксированы, идут ЭП
    done = "done"  # все согласовали и все слоты маршрута `signed`


class StopReason(StrEnum):
    """Почему маршрут остановлен (разделы 5.4 и 5.5)."""

    rebuilt = "rebuilt"  # собранный PDF другой
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


class RouteInputError(ValueError):
    """Маршрут собран неверно: нет участников, шаг меньше 1, слот у двух участников (ответ 400)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RouteConflictError(Exception):
    """Действие несовместимо с состоянием маршрута (ответ 409, `not_participant` это 404).

    Коды: `invalid_transition`, `not_participant`, `not_your_turn`, `image_required`, `plate_required`.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DocSlot(NamedTuple):
    """Пара «документ, слот»: где стоит подпись участника."""

    doc_id: str
    slot_id: str


@dataclass(frozen=True)
class DocSnapshot:
    """Отпечатки документа, которые маршрут видел последними (раздел 5.5).

    `compiled_sha256` сборка, отправленная на подписание: маршрут сам не пересобирает, поэтому за раунд она не
    меняется. `marks_digest` и `frozen_sha256` маршрут меняет сам (открывает картинки, фиксирует) и обновляет
    снимок после своих эффектов (`transitions.refresh_snapshot`); иное отличие это изменение вне маршрута.
    """

    compiled_sha256: str | None
    marks_digest: str
    frozen_sha256: str | None = None


@dataclass(frozen=True)
class Approval:
    """Согласие участника: какую версию документов он согласовал.

    `tokens` отпечаток сборки каждого его документа (`build:<sha>`, `engine.approval_token`). `phase` фаза
    маршрута в момент согласия: согласившие до фиксации (`approval`) подписывают ЭП после неё параллельно и не
    задерживают следующие шаги (раздел 4.2).
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

    @property
    def steps(self) -> tuple[int, ...]:
        """Номера шагов по возрастанию, без повторов."""
        return tuple(sorted({p.step for p in self.participants}))

    @property
    def pairs(self) -> tuple[DocSlot, ...]:
        """Все пары «документ, слот» маршрута."""
        return tuple(pair for p in self.participants for pair in p.assignments)

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

    Комментарий возврата хранится здесь (`details["comment"]`), а не в аудите.
    """

    route_id: UUID
    round: int
    at: datetime
    kind: EventKind
    actor_id: UUID | None = None
    participant_id: UUID | None = None
    details: Mapping[str, object] = field(default_factory=dict)
