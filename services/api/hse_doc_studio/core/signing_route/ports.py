"""Порты сценариев маршрута подписания: люди проекта и уведомления (docs/design/signing-route.md, 6.5 и 6.6).

Только серверный режим: локальная Студия маршрутов не ведёт (раздел 6.9). Реализации подставляет серверный
контейнер, тесты сценариев берут двойники.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.entities import SigningRoute


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
    """Люди проекта глазами маршрута: кто с какой персоной, кого пригласили, как кого зовут.

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


class ISigningNotifier(Protocol):
    """Уведомления маршрута: точка подключения среза R8 (раздел 6.6).

    Сценарий вызывает `notify` внутри своей транзакции, сразу после сохранения маршрута и событий, с теми
    уведомлениями, которые дал расчёт (`Notify` с видом, участниками, отправителем и ходом запроса). Запросы
    (`Notice.request`) сценарий уже отметил у участников (`mark_notified`): расчёт их не повторит, поэтому
    реализация доставляет каждое уведомление один раз. `actor_id` тот, чьё действие вызвало уведомления
    (None у сверки сервера); `comment` текст возврата на доработку для `signing_returned`.

    Письма уходят после транзакции (как у `INotifier`); исключение здесь откатывает действие целиком.
    До среза R8 подключена реализация без доставки.
    """

    async def notify(
        self,
        route: SigningRoute,
        notices: Sequence[Notify],
        *,
        actor_id: UUID | None,
        comment: str | None = None,
    ) -> None: ...
