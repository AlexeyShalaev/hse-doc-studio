"""Порты маршрута подписания вне хранилища: уведомления, люди проекта, факты документов, подписи, счётчик задач,
сторож других входов подписи и правок подписей, наблюдатель за изменениями проекта.

Только серверный режим (раздел 6.9). Реализации читают файлы проекта и шаблон или пишут во «Входящие»
(`use_cases/signing_route`), поэтому здесь только протоколы и значения.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.engine import RouteFacts
from hse_doc_studio.core.signing_route.entities import (
    TURN_STATES,
    DocSlot,
    ParticipantState,
    RoutePhase,
    RouteStatus,
    SigningRoute,
    StopReason,
)


class IBuildArchive(Protocol):
    """Архив прежних сборок документа: перенос маршрутов 0.20.0 ищет в нём согласованную сборку (12.11)."""

    async def find(self, project_id: UUID, folder: Path, doc_id: str, sha256: str) -> bytes | None:
        """PDF прежней сборки документа с этим sha256; None, если его в архиве нет."""
        ...


class ISigningNotifier(Protocol):
    """Доставка уведомлений маршрута во «Входящие» и письмом (раздел 6.6).

    Сценарий вызывает `notify` внутри своей транзакции, сразу после сохранения маршрута и событий, с уведомлениями
    расчёта и своими (`Notify`: вид, участники, отправитель, ход запроса). Запросы (`Notice.request`) сценарий уже
    отметил у участников (`mark_notified`, `notices.mark_requests`), поэтому реализация доставляет каждое
    уведомление один раз и маршрут не меняет. `actor_id` тот, чьё действие вызвало уведомления (None у сверки
    сервера); `comment` текст возврата на доработку для `signing_returned`. Откат транзакции откатывает и
    уведомления; письма уходят отдельной задачей, как у `INotifier`.
    """

    async def notify(
        self,
        route: SigningRoute,
        notices: Sequence[Notify],
        *,
        actor_id: UUID | None,
        comment: str | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class RouteCandidate:
    """Участник проекта с персоной: кого можно поставить в шаг маршрута (раздел 6.5)."""

    user_id: UUID
    name: str
    persona: str


@dataclass(frozen=True)
class RouteInvitee:
    """Ожидающее приглашение в проект с персоной: участник маршрута ждёт его принятия как `invited`.

    `name` имя аккаунта приглашённого или маска его почты (`p***@example.org`).
    """

    invitation_id: str
    persona: str
    name: str | None


class IRoutePeople(Protocol):
    """Люди проекта глазами сценариев автора: кто с какой персоной, кого пригласили, как кого зовут (6.5).

    Пользователи здесь UUID, как в сущностях маршрута; в хранилище это `users.id` (32 hex-символа).
    """

    async def candidates(self, project_id: UUID) -> list[RouteCandidate]:
        """Участники проекта с персоной: прямые записи с привязкой и владелец-человек solo-проекта как `author`.

        Порядок: владелец, затем участники по времени добавления. Отключённые аккаунты не входят.
        """
        ...

    async def invitees(self, project_id: UUID) -> list[RouteInvitee]:
        """Ожидающие и не просроченные приглашения проекта с персоной, новые первыми."""
        ...

    async def personas(self, project_id: UUID, user_ids: Collection[UUID]) -> dict[UUID, frozenset[str]]:
        """Персоны людей в проекте по их праву (как у подписи слота); ушедший из проекта получает пустое множество.

        По ним расчёт замечает ушедшего или сменившего персону участника (`RouteFacts.personas`).
        """
        ...

    async def names(self, user_ids: Collection[UUID]) -> dict[UUID, str]:
        """Имена аккаунтов; удалённого человека в ответе нет."""
        ...


class IRouteFacts(Protocol):
    """Факты документов маршрута сейчас (`RouteFacts`): сборки, видимый слой, состояние подписей, плашки.

    Чтение ничего не пишет. Персоны участников проекта (`RouteFacts.personas`) реализация не заполняет: уход
    участника замечают сторожа маршрута (срез R7), а экранам и задачам он не нужен.
    """

    async def facts(self, route: SigningRoute) -> RouteFacts | None:
        """None, если проект или версию шаблона не прочитать (проект удалён, пак снят)."""
        ...


@dataclass(frozen=True)
class RouteLabels:
    """Подписи маршрута для людей: название проекта и точки сдачи (`{ru, en}` из пака)."""

    project_name: str
    profile_name: Mapping[str, str] = field(default_factory=dict)
    # Названия документов проекта `{doc_id: {ru, en}}`: письмо о новой версии называет изменившиеся (12.6).
    doc_names: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def profile(self, lang: str | None, fallback: str) -> str:
        """Название точки на языке `lang`, иначе по-русски, иначе любое, иначе `fallback` (id точки)."""
        return _pick(self.profile_name, lang) or fallback

    def doc(self, lang: str | None, doc_id: str) -> str:
        """Название документа на языке `lang`, иначе по-русски, иначе любое, иначе его id."""
        return _pick(self.doc_names.get(doc_id, {}), lang) or doc_id


def _pick(names: Mapping[str, str], lang: str | None) -> str | None:
    return names.get(lang or "ru") or names.get("ru") or next(iter(names.values()), None)


class IRouteLabels(Protocol):
    async def labels(self, project_id: UUID, profile_id: str) -> RouteLabels | None:
        """None, если проекта нет. Точка, которой нет в паке, остаётся без названия."""
        ...


class ISigningTaskCounter(Protocol):
    """Сколько у человека задач «На подпись»: число в сводке «Входящих» (`InboxSummary.signing_tasks`)."""

    async def count_for_user(self, user_id: str) -> int: ...


@dataclass(frozen=True)
class RouteHold:
    """Идущий маршрут держит документ: что вправе сделать актор мимо страницы подписи (раздел 6.10).

    `signable` слоты документа, которые актор может подписать сейчас: он их участник и маршрут ждёт его подписи
    (`to_sign`). Пусто: не его очередь, документ для «Подписать комплект» закрыт.
    """

    route_id: UUID
    profile_id: str
    signable: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SigningDoc:
    """Документ идущего маршрута для пометки правки (раздел 12.10): правка и сборка его не останавливают, но в
    подписываемую версию не попадут. `sent_at` когда отправлена его версия на подписи (`doc_sent_at`)."""

    doc_id: str
    route_id: UUID
    sent_at: datetime | None


@dataclass(frozen=True)
class HeldRoute:
    """Маршрут, который держит документы проекта (`HOLDING_STATUSES`), по хранимому состоянию (signing-route.md, 13.3).

    Для отметки «Подпись необязательна»: какой точки маршрут, какие документы держит и какие пары включил, в том
    числе слоты сверх точки (`extra_slots`).
    """

    route_id: UUID
    profile_id: str
    docs: frozenset[str]
    pairs: frozenset[DocSlot]


@dataclass(frozen=True)
class PlanRoute:
    """Маршрут в ответе плана подписей (раздел 6.1): состояние по расчёту на текущих фактах, а не из хранилища.

    `current_step` номер текущего шага по порядку (с 1), None вне идущего маршрута; `steps_total` число шагов.
    `changed_docs` документы маршрута, рабочая сборка которых ушла от версии на подписи (12.9), в порядке маршрута.
    """

    id: UUID
    profile_id: str
    status: RouteStatus
    phase: RoutePhase | None
    round: int
    current_step: int | None
    steps_total: int
    stop_reason: StopReason | None = None
    changed_docs: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanRoutes:
    """Маршруты для плана подписей: маршрут точки или документа и состояния участников по их слотам.

    `held_docs` документы, которые держит идущий по расчёту маршрут: их фиксирует и подписывает только он, поэтому
    слот такого документа ждёт человека, лишь когда маршрут ждёт его самого (`is_turn`).
    """

    route: PlanRoute | None = None
    slot_states: Mapping[DocSlot, ParticipantState] = field(default_factory=dict)
    held_docs: frozenset[str] = frozenset()

    def is_turn(self, doc_id: str, slot_id: str) -> bool:
        """Слот можно делать сейчас: документ свободен или маршрут ждёт участника этого слота."""
        if doc_id not in self.held_docs:
            return True
        return self.slot_states.get(DocSlot(doc_id, slot_id)) in TURN_STATES


class ISigningRouteGate(Protocol):
    """Маршрут у входов мимо страницы подписи (разделы 5.5, 6.1 и 6.10).

    - другие входы подписи слота (КриптоПро, готовая подпись, «Подписать в Студии»): `require_turn` до записи
      подписи и `signature_written` после неё;
    - правки подписей документа идущего маршрута: `require_unlocked` до правки (409 `route_locked`);
    - «Подписать комплект» и `sign_submission`: `hold` говорит, держит ли документ маршрут и что актор вправе
      подписать;
    - план подписей: `plan_routes` даёт маршрут и состояния участников для ответа.

    Локальная Студия маршрутов не ведёт: там порт ничего не делает (`NoSigningRoutes`).
    """

    async def require_turn(self, project_id: UUID, doc_id: str, slot_id: str) -> UUID | None:
        """Слот идущего маршрута подписывает только его участник, когда маршрут ждёт его подписи.

        Иначе `RouteConflictError` с кодом `not_your_turn` (409). Слот вне маршрута и документ без идущего
        маршрута проходят без проверки. Возвращает id маршрута, в очередь которого подписывается слот (None вне
        маршрута): подпись под `signing_route_scope` попадает в журнал аудита с `route_id` (раздел 6.7).
        """
        ...

    async def signature_written(self, project_id: UUID, doc_id: str, slot_id: str) -> None:
        """Подпись слота записана: пересчитать маршрут, который держит документ (событие, запросы, завершение).

        Сбой пересчёта подпись не отменяет: она уже в файлах проекта, маршрут догонит её при следующем расчёте.
        Вызывать вне `project_lock`: пересчёт берёт строку маршрута, затем `project_lock`.
        """
        ...

    async def signatures_written(self, project_id: UUID, slots: Sequence[DocSlot]) -> None:
        """То же для нескольких слотов разом («Подписать комплект»): один пересчёт на маршрут, а не на слот."""
        ...

    async def require_unlocked(
        self, project_id: UUID, *, doc_id: str | None = None, slot_id: str | None = None
    ) -> None:
        """Правка подписей мимо маршрута: `RouteConflictError` с кодом `route_locked` (409), если она задевает
        документ идущего маршрута.

        `doc_id` правка документа (размещение, фиксация и её снятие, удаление открепленной подписи). `slot_id`
        правка слота, общего для документов проекта (настройка, картинка, подписант плашки): закрыта, если слот
        входит в идущий маршрут или размещён на его документе. Остановленный, возвращённый и завершённый маршрут
        правку не запрещает, как и маршрут, который по расчёту уже не идёт. Только читает: под `project_lock`
        вызывать можно.
        """
        ...

    async def require_not_held(self, project_id: UUID, doc_id: str) -> None:
        """«Подписывать текущую сборку» (раздел 12.4): `RouteConflictError` с кодом `route_locked` (409), если
        документ держит маршрут (`HOLDING_STATUSES`, в том числе остановленный и завершённый). Документ освобождают
        отмена маршрута или «Снять с контроля». Только читает: под `project_lock` вызывать можно."""
        ...

    async def hold(self, project_id: UUID, doc_id: str) -> RouteHold | None:
        """Идущий маршрут, который держит документ, и слоты, которые актор вправе подписать сейчас; None, если
        документ свободен. Только читает: под `project_lock` вызывать можно."""
        ...

    async def on_signing(self, project_id: UUID) -> tuple[SigningDoc, ...]:
        """Документы проекта, которые держит идущий маршрут (`active`), в порядке маршрутов и их документов: для
        пометки `signing_note` у тулов MCP, которые правят и собирают (раздел 12.10). Только читает."""
        ...

    async def plan_routes(
        self, project_id: UUID, *, profile_id: str | None = None, doc_id: str | None = None
    ) -> PlanRoutes:
        """Маршрут для плана подписей: точки (`profile_id`), иначе документа (`doc_id`), и состояния участников
        по слотам документов, которые держат маршруты проекта. Чтение ничего не пишет. Гостю и тому, кто открыл
        проект по ссылке, маршрут не раскрывается (раздел 7): ответ пустой."""
        ...

    async def held_routes(self, project_id: UUID) -> tuple[HeldRoute, ...]:
        """Маршруты проекта, которые держат документы (`HOLDING_STATUSES`), по хранимому состоянию, без расчёта
        (раздел 13.3). Только читает: под `project_lock` вызывать можно. Гостю и тому, кто открыл проект по ссылке,
        маршрут не раскрывается: ответ пустой."""
        ...


class NoSigningRoutes:
    """`ISigningRouteGate` там, где маршрутов нет (локальная Студия): подписи правятся и ставятся как обычно."""

    async def require_turn(self, project_id: UUID, doc_id: str, slot_id: str) -> UUID | None:
        return None

    async def signature_written(self, project_id: UUID, doc_id: str, slot_id: str) -> None:
        return None

    async def signatures_written(self, project_id: UUID, slots: Sequence[DocSlot]) -> None:
        return None

    async def require_unlocked(
        self, project_id: UUID, *, doc_id: str | None = None, slot_id: str | None = None
    ) -> None:
        return None

    async def require_not_held(self, project_id: UUID, doc_id: str) -> None:
        return None

    async def hold(self, project_id: UUID, doc_id: str) -> RouteHold | None:
        return None

    async def on_signing(self, project_id: UUID) -> tuple[SigningDoc, ...]:
        return ()

    async def plan_routes(
        self, project_id: UUID, *, profile_id: str | None = None, doc_id: str | None = None
    ) -> PlanRoutes:
        return PlanRoutes()

    async def held_routes(self, project_id: UUID) -> tuple[HeldRoute, ...]:
        return ()


class IRouteWatch(Protocol):
    """Наблюдатель за изменениями проекта мимо маршрута (раздел 5.5): сборка, запись состояния подписей,
    синхронизация, восстановление из истории, уход участника.

    `on_project_changed` только ставит сверку маршрутов проекта в очередь: не блокирует, не бросает и ничего не
    блокирует сам, поэтому вызывать его можно откуда угодно, в том числе под `project_lock` и внутри сценария
    маршрута. Сверка идёт отдельной задачей в своей транзакции: строка маршрута, затем `project_lock`.
    """

    def on_project_changed(self, project_id: UUID) -> None: ...


class NoRouteWatch:
    """`IRouteWatch` там, где маршрутов нет (локальная Студия)."""

    def on_project_changed(self, project_id: UUID) -> None:
        return None
