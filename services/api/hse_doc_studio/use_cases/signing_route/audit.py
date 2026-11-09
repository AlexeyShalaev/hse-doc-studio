"""Запись маршрута подписания в журнал аудита сервера (docs/design/signing-route.md, раздел 6.7).

`SigningRouteAudit` пишет записи `signing_route.*` с целью «проект»: в журнале они видны и в общем списке, и по
фильтру «все события этого объекта». `AuditedSigningRoutes` это хранилище маршрутов, которое вместе с событиями
истории пишет их записи журнала: кто бы ни сохранил событие (сценарий автора или подписанта, сторож другого входа
подписи, автонапоминание, сверка), оно попадает в аудит в той же транзакции. Действия без события истории
(черновик, правка, снятие с контроля, способ, плашка и картинка подписанта) сценарии записывают сами.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from uuid import UUID

from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.signing_route.audit import RouteAuditRecord, audit_of_event
from hse_doc_studio.core.signing_route.entities import RouteEvent, RouteStatus, SigningRoute
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository


class SigningRouteAudit:
    def __init__(self, audit: IAuditLog) -> None:
        self._audit = audit

    async def write(self, route: SigningRoute, record: RouteAuditRecord) -> None:
        project = str(route.project_id)
        await self._audit.record(
            record.action.value,
            actor_id=record.actor_id.hex if record.actor_id is not None else None,
            target=project,
            details={"project_id": project, **record.details},
        )

    async def events(self, route: SigningRoute, events: Sequence[RouteEvent]) -> None:
        """Записи журнала о событиях истории, сохранённых вместе с маршрутом `route`."""
        for event in events:
            record = audit_of_event(route, event)
            if record is not None:
                await self.write(route, record)


class AuditedSigningRoutes:
    """`ISigningRouteRepository` с аудитом: запись маршрута с событиями пишет и их записи журнала."""

    def __init__(self, routes: ISigningRouteRepository, audit: SigningRouteAudit) -> None:
        self._routes = routes
        self._audit = audit

    @property
    def storage(self) -> ISigningRouteRepository:
        """Хранилище, записи которого сопровождает аудит."""
        return self._routes

    async def add(self, route: SigningRoute, *, events: Sequence[RouteEvent] = ()) -> SigningRoute:
        saved = await self._routes.add(route, events=events)
        await self._audit.events(saved, events)
        return saved

    async def save(self, route: SigningRoute, *, events: Sequence[RouteEvent] = ()) -> SigningRoute:
        saved = await self._routes.save(route, events=events)
        await self._audit.events(saved, events)
        return saved

    async def get(self, project_id: UUID, route_id: UUID, *, lock: bool = False) -> SigningRoute | None:
        return await self._routes.get(project_id, route_id, lock=lock)

    async def get_open(self, project_id: UUID, profile_id: str, *, lock: bool = False) -> SigningRoute | None:
        return await self._routes.get_open(project_id, profile_id, lock=lock)

    async def list_for_project(
        self, project_id: UUID, *, profile_id: str | None = None, statuses: Collection[RouteStatus] | None = None
    ) -> list[SigningRoute]:
        return await self._routes.list_for_project(project_id, profile_id=profile_id, statuses=statuses)

    async def holding(self, project_id: UUID, doc_id: str) -> SigningRoute | None:
        return await self._routes.holding(project_id, doc_id)

    async def list_watching(self, project_id: UUID | None = None) -> list[SigningRoute]:
        return await self._routes.list_watching(project_id)

    async def list_for_user(
        self, user_id: UUID, *, project_id: UUID | None = None, statuses: Collection[RouteStatus] | None = None
    ) -> list[SigningRoute]:
        return await self._routes.list_for_user(user_id, project_id=project_id, statuses=statuses)

    async def list_for_invitation(self, project_id: UUID, invitation_id: str) -> list[SigningRoute]:
        return await self._routes.list_for_invitation(project_id, invitation_id)

    async def list_events(self, route_id: UUID, *, round: int | None = None) -> list[RouteEvent]:
        return await self._routes.list_events(route_id, round=round)
