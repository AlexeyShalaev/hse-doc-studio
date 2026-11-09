"""Порты маршрута подписания вне хранилища: уведомления, факты документов, подписи для людей, счётчик задач.

Только серверный режим (раздел 6.9). Реализации читают файлы проекта и шаблон или пишут во «Входящие»
(`use_cases/signing_route`), поэтому здесь только протоколы и значения.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
