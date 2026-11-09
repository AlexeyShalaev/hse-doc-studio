"""InMemory-реализация хранилища маршрутов подписания: те же правила, что у Postgres (контракт в tests/contract)."""

from __future__ import annotations

import copy
import itertools
from collections.abc import Callable, Collection, Sequence
from dataclasses import replace
from uuid import UUID

from hse_doc_studio.core.signing_route.entities import (
    HOLDING_STATUSES,
    OPEN_STATUSES,
    WATCHING_STATUSES,
    RouteEvent,
    RouteStatus,
    SigningRoute,
)
from hse_doc_studio.core.signing_route.repositories import (
    DocumentOnRouteError,
    OpenRouteExistsError,
    StaleRouteError,
)


class InMemorySigningRouteRepository:
    """Хранит копии маршрутов: правка возвращённого маршрута не меняет сохранённый, как в базе."""

    def __init__(self) -> None:
        self._routes: dict[UUID, SigningRoute] = {}
        self._created: dict[UUID, int] = {}
        self._events: list[RouteEvent] = []
        self._seq = itertools.count()

    async def add(self, route: SigningRoute, *, events: Sequence[RouteEvent] = ()) -> SigningRoute:
        if route.version != 0:
            raise ValueError(f"signing route {route.id} is already stored (version {route.version})")
        if route.id in self._routes:
            raise ValueError(f"signing route {route.id} already exists")
        _check_events(route, events)
        return self._store(replace(route, version=1), events, created=next(self._seq))

    async def save(self, route: SigningRoute, *, events: Sequence[RouteEvent] = ()) -> SigningRoute:
        _check_events(route, events)
        current = self._routes.get(route.id)
        if current is None or current.project_id != route.project_id or current.version != route.version:
            raise StaleRouteError(route.id)
        return self._store(replace(route, version=route.version + 1), events, created=self._created[route.id])

    async def get(self, project_id: UUID, route_id: UUID, *, lock: bool = False) -> SigningRoute | None:
        found = self._routes.get(route_id)
        return copy.deepcopy(found) if found is not None and found.project_id == project_id else None

    async def get_open(self, project_id: UUID, profile_id: str, *, lock: bool = False) -> SigningRoute | None:
        found = self._select(
            lambda r: r.project_id == project_id and r.profile_id == profile_id and r.status in OPEN_STATUSES
        )
        return found[0] if found else None

    async def list_for_project(
        self, project_id: UUID, *, profile_id: str | None = None, statuses: Collection[RouteStatus] | None = None
    ) -> list[SigningRoute]:
        return self._select(
            lambda r: (
                r.project_id == project_id
                and (profile_id is None or r.profile_id == profile_id)
                and (statuses is None or r.status in statuses)
            )
        )

    async def holding(self, project_id: UUID, doc_id: str) -> SigningRoute | None:
        found = self._select(lambda r: r.project_id == project_id and r.status in HOLDING_STATUSES and doc_id in r.docs)
        return found[0] if found else None

    async def list_watching(self, project_id: UUID | None = None) -> list[SigningRoute]:
        return self._select(
            lambda r: r.status in WATCHING_STATUSES and (project_id is None or r.project_id == project_id)
        )

    async def list_for_user(
        self, user_id: UUID, *, project_id: UUID | None = None, statuses: Collection[RouteStatus] | None = None
    ) -> list[SigningRoute]:
        return self._select(
            lambda r: (
                any(p.user_id == user_id for p in r.participants)
                and (project_id is None or r.project_id == project_id)
                and (statuses is None or r.status in statuses)
            )
        )

    async def list_for_invitation(self, project_id: UUID, invitation_id: str) -> list[SigningRoute]:
        return self._select(
            lambda r: r.project_id == project_id and any(p.invitation_id == invitation_id for p in r.participants)
        )

    async def list_events(self, route_id: UUID, *, round: int | None = None) -> list[RouteEvent]:
        return [
            copy.deepcopy(e) for e in self._events if e.route_id == route_id and (round is None or e.round == round)
        ]

    def _select(self, keep: Callable[[SigningRoute], bool]) -> list[SigningRoute]:
        found = [r for r in self._routes.values() if keep(r)]
        found.sort(key=lambda r: self._created[r.id], reverse=True)
        return copy.deepcopy(found)

    def _store(self, route: SigningRoute, events: Sequence[RouteEvent], *, created: int) -> SigningRoute:
        _check_events(route, events)
        others = [r for r in self._routes.values() if r.id != route.id and r.project_id == route.project_id]
        if route.status in OPEN_STATUSES and any(
            r.profile_id == route.profile_id and r.status in OPEN_STATUSES for r in others
        ):
            raise OpenRouteExistsError(route.project_id, route.profile_id)
        if route.status in HOLDING_STATUSES:
            held = {doc_id for r in others if r.status in HOLDING_STATUSES for doc_id in r.docs}
            if busy := [doc_id for doc_id in route.docs if doc_id in held]:
                raise DocumentOnRouteError(busy)
        self._routes[route.id] = copy.deepcopy(route)
        self._created[route.id] = created
        self._events.extend(copy.deepcopy(list(events)))
        return route


def _check_events(route: SigningRoute, events: Sequence[RouteEvent]) -> None:
    strangers = [event for event in events if event.route_id != route.id]
    if strangers:
        raise ValueError(f"events of route {strangers[0].route_id} cannot be stored with route {route.id}")
