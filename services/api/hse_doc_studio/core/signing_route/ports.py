"""Порты маршрута подписания вне хранилища: факты документов, подписи для экранов и писем, счётчик задач.

Реализации читают файлы проекта и шаблон (`use_cases/signing_route`), поэтому здесь только протоколы и значения.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.signing_route.engine import RouteFacts
from hse_doc_studio.core.signing_route.entities import SigningRoute


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
