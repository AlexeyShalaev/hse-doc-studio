"""Маршруты в пересчёте мест на якорях после сборки (docs/design/signing-route.md, 15.17.9).

Документ, который держит маршрут (`HOLDING_STATUSES`), пересборка не трогает: его подписывают по версии на подписи,
место меняется только в сценарии маршрута при новой версии. Пары черновиков маршрута на документе без места или с
затравкой получают место пресета, как при создании черновика: студент правит текст и после того, как черновик создан.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.signatures.pack_places import SourceAnchors
from hse_doc_studio.core.signing_route.entities import RouteStatus
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.signatures.pack_places import PackPlaces
from hse_doc_studio.use_cases.signing_route.preset import INHERITED_ORIGINS, apply_places, has_preset
from hse_doc_studio.use_cases.signing_route.scenario import RouteServices


class RouteDraftPlaces:
    """`IRouteDraftPlaces` сервера: только читает маршруты проекта, состояние подписей пишет вызывающий."""

    def __init__(self, services: RouteServices) -> None:
        self._s = services

    async def apply(
        self, project_id: UUID, doc_id: str, state: SignaturesState, src: SourceAnchors
    ) -> SignaturesState | None:
        if await self._s.routes.holding(project_id, doc_id) is not None:
            return None
        drafts = await self._s.routes.list_for_project(project_id, statuses=(RouteStatus.draft,))
        for route in drafts:
            pairs = [pair for pair in route.pairs if pair.doc_id == doc_id]
            if not pairs:
                continue
            try:
                point = await self._s.points.load(project_id, route.profile_id)
            except NotFoundError:
                continue
            if not has_preset(point.version, point.profile):
                continue
            anchors = {doc_id: src}
            places = PackPlaces.load(self._s.points.templates, point.project, point.version, anchors)
            state, _ = apply_places(point, state, pairs, places, origins=INHERITED_ORIGINS, anchors=anchors)
        return state


class ScopedRouteDraftPlaces:
    """`IRouteDraftPlaces` для пересчёта после сборки: хуки сборки живут дольше запроса, поэтому маршруты читаются в
    своём запросном окружении на каждый вызов (`scope` даёт `RouteDraftPlaces` нового окружения)."""

    def __init__(self, scope: Callable[[], AbstractAsyncContextManager[RouteDraftPlaces]]) -> None:
        self._scope = scope

    async def apply(
        self, project_id: UUID, doc_id: str, state: SignaturesState, src: SourceAnchors
    ) -> SignaturesState | None:
        async with self._scope() as drafts:
            return await drafts.apply(project_id, doc_id, state, src)
