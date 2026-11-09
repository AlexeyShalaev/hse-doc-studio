"""Порты маршрута подписания вне хранилища: уведомления, люди проекта, факты документов, подписи, счётчик задач
и сторож других входов подписи.

Только серверный режим (раздел 6.9). Реализации читают файлы проекта и шаблон или пишут во «Входящие»
(`use_cases/signing_route`), поэтому здесь только протоколы и значения.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.engine import RouteFacts
from hse_doc_studio.core.signing_route.entities import SigningRoute


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

    def profile(self, lang: str | None, fallback: str) -> str:
        """Название точки на языке `lang`, иначе по-русски, иначе любое, иначе `fallback` (id точки)."""
        names = self.profile_name
        return names.get(lang or "ru") or names.get("ru") or next(iter(names.values()), None) or fallback


class IRouteLabels(Protocol):
    async def labels(self, project_id: UUID, profile_id: str) -> RouteLabels | None:
        """None, если проекта нет. Точка, которой нет в паке, остаётся без названия."""
        ...


class ISigningTaskCounter(Protocol):
    """Сколько у человека задач «На подпись»: число в сводке «Входящих» (`InboxSummary.signing_tasks`)."""

    async def count_for_user(self, user_id: str) -> int: ...


class ISigningRouteGate(Protocol):
    """Маршрут у других входов подписи слота: КриптоПро, готовая подпись, «Подписать в Студии» (раздел 6.10).

    Ручки плана подписей вызывают `require_turn` до записи подписи и `signature_written` после неё. Локальная
    Студия маршрутов не ведёт: там порт ничего не делает (`NoSigningRoutes`).
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
        """
        ...


class NoSigningRoutes:
    """`ISigningRouteGate` там, где маршрутов нет (локальная Студия): слот подписывается как обычно."""

    async def require_turn(self, project_id: UUID, doc_id: str, slot_id: str) -> UUID | None:
        return None

    async def signature_written(self, project_id: UUID, doc_id: str, slot_id: str) -> None:
        return None
