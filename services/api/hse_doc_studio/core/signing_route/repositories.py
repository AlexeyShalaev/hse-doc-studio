"""Хранилище маршрутов подписания (docs/design/signing-route.md, раздел 5.8).

Маршруты живут в Postgres сервера; локальная Студия их не хранит (раздел 6.9), поэтому порт есть только в
серверном контейнере. Хранилище держит три правила, которые нельзя проверить без него:

- на точку сдачи (`project_id`, `profile_id`) не больше одного незавершённого маршрута (`OPEN_STATUSES`);
- документ проекта держит не больше одного маршрута (`HOLDING_STATUSES`): иначе две очереди подписали бы его
  наперегонки;
- запись идёт только поверх той версии, что прочитана (`SigningRoute.version`): одновременные действия
  подписантов не затирают друг друга, второй перечитывает маршрут и повторяет расчёт.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signing_route.entities import RouteConflictError, RouteEvent, RouteStatus, SigningRoute


class StaleRouteError(RouteConflictError):
    """Маршрут перезаписан после чтения или удалён вместе с проектом: перечитать и повторить действие."""

    def __init__(self, route_id: UUID) -> None:
        super().__init__(
            "stale_route",
            localized_error(
                "Маршрут подписания изменился, откройте его заново", "The signing route has changed, reload it"
            ),
        )
        self.route_id = route_id


class OpenRouteExistsError(RouteConflictError):
    """У точки сдачи уже есть незавершённый маршрут (`draft`, `active`, `paused`, `returned`)."""

    def __init__(self, project_id: UUID, profile_id: str) -> None:
        super().__init__(
            "route_exists",
            localized_error(
                "У этой контрольной точки уже есть незавершённый маршрут подписания",
                "This submission checkpoint already has an unfinished signing route",
            ),
        )
        self.project_id = project_id
        self.profile_id = profile_id


class DocumentOnRouteError(RouteConflictError):
    """Документ уже держит другой маршрут (идёт, остановлен или завершён и следит за документом)."""

    def __init__(self, doc_ids: Sequence[str]) -> None:
        super().__init__(
            "doc_on_route",
            localized_error(
                "Документ уже на подписании по другому маршруту", "The document is already on another signing route"
            ),
        )
        self.doc_ids = tuple(doc_ids)


class ISigningRouteRepository(Protocol):
    """Маршруты с участниками и снимком, история событий.

    Маршрут читается и пишется целиком: участники, документы, согласия, запросы и снимок возвращаются ровно такими,
    какими сохранены, в том же порядке. Списки отдают новые маршруты первыми (по времени создания записи).
    `lock=True` блокирует строку маршрута до конца транзакции (`SELECT … FOR UPDATE`); смысл это имеет только
    внутри `IUnitOfWork.begin()`, где сценарий делает переход и сохраняет его. Id участника уникален в своём
    маршруте, новый маршрут может взять состав прежнего вместе с id. `details` события хранятся как JSON: строки,
    числа, списки и словари (кортеж вернётся списком).
    """

    async def add(self, route: SigningRoute, *, events: Sequence[RouteEvent] = ()) -> SigningRoute:
        """Новый маршрут (`version` 0) вместе с событиями; возвращает его с `version` 1.

        `OpenRouteExistsError`, если маршрут незавершённый, а у точки уже есть такой; `DocumentOnRouteError`, если
        маршрут держит документы, а документ держит другой маршрут. При ошибке ничего не записано.
        """
        ...

    async def save(self, route: SigningRoute, *, events: Sequence[RouteEvent] = ()) -> SigningRoute:
        """Записать маршрут поверх прочитанной версии и добавить события; возвращает его со следующей `version`.

        Событие с `id` уже записано: у него обновляются `at` и `details`, вид и маршрут должны совпасть, иначе
        `ValueError` (склейка подряд идущих `marks_edited`, раздел 14.6).

        `StaleRouteError`, если версия в хранилище другая или маршрута уже нет. Правила точки и документов как у
        `add`: отправить заново отменённый маршрут нельзя, пока у точки есть другой незавершённый. При любой
        ошибке ничего не записано.
        """
        ...

    async def get(self, project_id: UUID, route_id: UUID, *, lock: bool = False) -> SigningRoute | None:
        """Маршрут проекта; маршрут другого проекта не находится."""
        ...

    async def get_open(self, project_id: UUID, profile_id: str, *, lock: bool = False) -> SigningRoute | None:
        """Незавершённый маршрут точки сдачи (не больше одного)."""
        ...

    async def list_for_project(
        self, project_id: UUID, *, profile_id: str | None = None, statuses: Collection[RouteStatus] | None = None
    ) -> list[SigningRoute]:
        """Маршруты проекта, при `profile_id` только этой точки, при `statuses` только в этих статусах."""
        ...

    async def holding(self, project_id: UUID, doc_id: str) -> SigningRoute | None:
        """Маршрут, который держит документ (`HOLDING_STATUSES`): сторожа правок подписей и очереди (6.10)."""
        ...

    async def list_watching(self, project_id: UUID | None = None) -> list[SigningRoute]:
        """Маршруты, которые сверяют документы со снимком (`WATCHING_STATUSES`): проекта или все.

        Хуки изменения проекта сверяют маршруты одного проекта, периодическая сверка лидера все (раздел 5.5).
        """
        ...

    async def list_holding(self) -> list[SigningRoute]:
        """Маршруты сервера, которые держат документы (`HOLDING_STATUSES`): разовый перенос 0.20.0 (12.11)."""
        ...

    async def list_for_user(
        self, user_id: UUID, *, project_id: UUID | None = None, statuses: Collection[RouteStatus] | None = None
    ) -> list[SigningRoute]:
        """Маршруты, где пользователь участник, по всем проектам или одного.

        «На подпись» берёт идущие (`active`) и по расчёту оставляет те, где его очередь; уход участника из проекта
        ищет маршруты этого проекта.
        """
        ...

    async def list_for_invitation(self, project_id: UUID, invitation_id: str) -> list[SigningRoute]:
        """Маршруты проекта с участником, который ждёт этого приглашения: при принятии он получает `user_id`."""
        ...

    async def list_events(self, route_id: UUID, *, round: int | None = None) -> list[RouteEvent]:
        """История маршрута в порядке записи, при `round` только этого раунда."""
        ...
