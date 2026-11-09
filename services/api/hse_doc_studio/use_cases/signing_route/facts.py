"""Факты для расчёта маршрута: сборки документов, состояние подписей, данные плашек и персоны участников.

`RouteFacts.withheld` берётся из `SignaturesState.withheld` (раздел 6.1): без него расчёт решил бы, что ничего не
придержано, и каждый раз придерживал бы картинки заново.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.repositories import ISignatureRepository
from hse_doc_studio.core.signatures.plan import DocFacts, VisibleMark, mark_of
from hse_doc_studio.core.signatures.ports import ISignerPlateData
from hse_doc_studio.core.signing_route.engine import RouteFacts
from hse_doc_studio.core.signing_route.entities import SigningRoute
from hse_doc_studio.core.signing_route.ports import IRoutePeople
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo
from hse_doc_studio.use_cases.signatures.get_signature_plan import doc_facts
from hse_doc_studio.use_cases.signing_route.point import RoutePoint, RoutePointLoader


@dataclass(frozen=True)
class LoadedFacts:
    state: SignaturesState
    facts: RouteFacts

    @property
    def personas(self) -> Mapping[UUID, frozenset[str]]:
        return {user_id: frozenset(found) for user_id, found in (self.facts.personas or {}).items()}


class RouteFactsLoader:
    def __init__(
        self,
        points: RoutePointLoader,
        signature_repo: ISignatureRepository,
        plate_data: ISignerPlateData,
        people: IRoutePeople,
    ) -> None:
        self._points = points
        self._signatures = signature_repo
        self._plate_data = plate_data
        self._people = people

    async def load(self, point: RoutePoint, route: SigningRoute) -> LoadedFacts:
        """Что известно о документах маршрута сейчас; документ вне проекта считается несобранным."""
        project = point.project
        state = self._signatures.get_state(project.folder)
        docs: dict[str, DocFacts] = {}
        for doc_id in route.docs:
            document = point.documents.get(doc_id)
            if document is not None:
                docs[doc_id] = await doc_facts(project, point.version, document, state, self._points.template_service)
        users = [p.user_id for p in route.participants if p.user_id is not None]
        personas = await self._people.personas(project.id, users)
        facts = RouteFacts(
            docs=docs,
            state=state,
            withheld=dict(state.withheld),
            plates=await self._plates(route, state),
            personas=personas,
        )
        return LoadedFacts(state, facts)

    async def _plates(self, route: SigningRoute, state: SignaturesState) -> dict[UUID, SignerInfo]:
        """Известные данные плашки по участникам: первый слот с плашкой, для которого порт их знает (6.5)."""
        plates: dict[UUID, SignerInfo] = {}
        for p in route.participants:
            if p.user_id is None:
                continue
            for pair in p.assignments:
                if mark_of(state.slots.get(pair.slot_id)) is not VisibleMark.plate:
                    continue
                found = await self._plate_data.plate_for(state, pair.slot_id, p.user_id.hex)
                if found is not None:
                    plates[p.user_id] = found
                    break
        return plates
