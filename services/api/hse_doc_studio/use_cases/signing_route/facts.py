"""Факты для расчёта маршрута и подписи маршрута для людей: всё, что читается из файлов проекта и шаблона.

Факты те же, что считает план подписей (`doc_facts`): хэш текущей сборки, отпечаток видимого слоя без придержанных
слотов, состояние подписей. `RouteFacts.withheld` берётся из `SignaturesState.withheld` (раздел 6.1): без него
расчёт решил бы, что ничего не придержано, и каждый раз придерживал бы картинки заново. Данные плашек по участникам
даёт порт открытых данных подписанта (`ISignerPlateData`, раздел 6.5).

Расчёт фактов один (`route_facts`), читателей два:

- `RouteFactsLoader` для сценариев автора и подписанта: точка сдачи уже загружена, нужны персоны участников проекта
  (уход участника) и расчёт на ещё не записанном состоянии подписей (проверка действия до записи файлов);
- `ProjectRouteFacts` для задач «На подпись», хука приглашения и уведомлений (`IRouteFacts`, `IRouteLabels`): проект
  находится по маршруту, персоны не нужны. Чтение ничего не пишет.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService, SubmissionProfileService
from hse_doc_studio.core.signatures.plan import DocFacts
from hse_doc_studio.core.signatures.ports import ISignerPlateData
from hse_doc_studio.core.signing_route.engine import RouteFacts
from hse_doc_studio.core.signing_route.entities import SigningRoute
from hse_doc_studio.core.signing_route.ports import IRoutePeople, RouteLabels
from hse_doc_studio.core.team import is_doc_active
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures.get_signature_plan import doc_facts
from hse_doc_studio.use_cases.signing_route.point import RoutePoint, RoutePointLoader


async def known_plates(
    route: SigningRoute, state: SignaturesState, plate_data: ISignerPlateData
) -> dict[UUID, SignerInfo]:
    """Известные данные плашки по участникам: первое, что порт знает по слотам участника (раздел 6.5).

    Спрашиваются все слоты участника, а не только слоты с плашкой: подписант картинкой может сменить способ на ЭП
    на своём шаге, и странице подписи нужно знать, известен ли его ключ. Расчёт берёт эти данные только для плашек.
    """
    plates: dict[UUID, SignerInfo] = {}
    for p in route.participants:
        if p.user_id is None or p.user_id in plates:
            continue
        for slot_id in dict.fromkeys(pair.slot_id for pair in p.assignments):
            found = await plate_data.plate_for(state, slot_id, p.user_id.hex)
            if found is not None:
                plates[p.user_id] = found
                break
    return plates


async def route_facts(  # noqa: PLR0913 — входы одного расчёта
    project: Project,
    version: TemplateVersion,
    route: SigningRoute,
    state: SignaturesState,
    template_service: ProjectTemplateService,
    plate_data: ISignerPlateData,
    *,
    personas: Mapping[UUID, Collection[str]] | None = None,
) -> RouteFacts:
    """Что известно о документах маршрута при состоянии подписей `state`.

    Документ вне проекта (удалён, выключен в команде) остаётся без фактов и считается несобранным.
    """
    documents = {doc.id: doc for doc in project.documents if is_doc_active(project, doc)}
    docs: dict[str, DocFacts] = {}
    for doc_id in route.docs:
        document = documents.get(doc_id)
        if document is not None:
            docs[doc_id] = await doc_facts(project, version, document, state, template_service)
    return RouteFacts(
        docs=docs,
        state=state,
        withheld=dict(state.withheld),
        plates=await known_plates(route, state, plate_data),
        personas=personas,
    )


@dataclass(frozen=True)
class LoadedFacts:
    state: SignaturesState
    facts: RouteFacts

    @property
    def personas(self) -> Mapping[UUID, frozenset[str]]:
        return {user_id: frozenset(found) for user_id, found in (self.facts.personas or {}).items()}


class RouteFactsLoader:
    """Факты для сценариев маршрута: точка сдачи уже загружена, персоны участников берутся из проекта."""

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

    async def load(self, point: RoutePoint, route: SigningRoute, state: SignaturesState | None = None) -> LoadedFacts:
        """Что известно о документах маршрута сейчас.

        `state` состояние подписей, которое сценарий только собирается записать (смена способа, данные плашки):
        расчёт на нём проверяет действие до записи файлов. Без него читается состояние с диска.
        """
        project = point.project
        current = state if state is not None else self._signatures.get_state(project.folder)
        users = [p.user_id for p in route.participants if p.user_id is not None]
        facts = await route_facts(
            project,
            point.version,
            route,
            current,
            self._points.template_service,
            self._plate_data,
            personas=await self._people.personas(project.id, users),
        )
        return LoadedFacts(current, facts)


@dataclass(frozen=True)
class _Loaded:
    project: Project
    version: TemplateVersion | None


class ProjectRouteFacts:
    """`IRouteFacts` и `IRouteLabels`: читает проект маршрута с диска; ничего не пишет."""

    def __init__(  # noqa: PLR0913 — порты перечислены явно
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        templates: ITemplateRepository,
        signatures: ISignatureRepository,
        template_service: ProjectTemplateService,
        plates: ISignerPlateData,
    ) -> None:
        self._projects = GetProjectUC(project_repo, project_index_repo)
        self._templates = templates
        self._signatures = signatures
        self._template_service = template_service
        self._plates = plates
        self._profiles = SubmissionProfileService()

    async def facts(self, route: SigningRoute) -> RouteFacts | None:
        loaded = await self._load(route.project_id)
        if loaded is None or loaded.version is None:
            return None
        state = self._signatures.get_state(loaded.project.folder)
        return await route_facts(loaded.project, loaded.version, route, state, self._template_service, self._plates)

    async def labels(self, project_id: UUID, profile_id: str) -> RouteLabels | None:
        loaded = await self._load(project_id)
        if loaded is None:
            return None
        profile = self._profiles.get_profile(loaded.version, profile_id) if loaded.version is not None else None
        return RouteLabels(project_name=loaded.project.name, profile_name=dict(profile.name) if profile else {})

    async def _load(self, project_id: UUID) -> _Loaded | None:
        try:
            project = (await self._projects.execute(GetProjectInput(project_id=project_id))).project
        except NotFoundError:
            return None
        lock = project.lock
        return _Loaded(project, self._templates.get_version(lock.pack_id, lock.template_id, lock.version))
