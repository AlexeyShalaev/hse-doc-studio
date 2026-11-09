"""Факты документов маршрута и подписи для людей из файлов проекта и шаблона (`IRouteFacts`, `IRouteLabels`).

Факты те же, что считает план подписей (`doc_facts`): хэш текущей сборки, отпечаток видимого слоя без
придержанных слотов, состояние подписей; плашки по участникам из порта открытых данных подписанта (срез R10).
"""

from __future__ import annotations

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
from hse_doc_studio.core.signing_route.ports import RouteLabels
from hse_doc_studio.core.value_objects import SignaturesState, SignerInfo
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures.get_signature_plan import doc_facts


@dataclass(frozen=True)
class _Loaded:
    project: Project
    version: TemplateVersion | None


class ProjectRouteContext:
    """Читает проект маршрута с диска; ничего не пишет."""

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
        project, version = loaded.project, loaded.version
        state = self._signatures.get_state(project.folder)
        documents = {doc.id: doc for doc in project.documents}
        docs: dict[str, DocFacts] = {}
        for doc_id in route.docs:
            doc = documents.get(doc_id)
            if doc is not None:
                docs[doc_id] = await doc_facts(project, version, doc, state, self._template_service)
        return RouteFacts(
            docs=docs, state=state, withheld=state.withheld, plates=await self._known_plates(route, state)
        )

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

    async def _known_plates(self, route: SigningRoute, state: SignaturesState) -> dict[UUID, SignerInfo]:
        """Известные данные плашки участника по его слотам: первое, что знает порт открытых данных."""
        plates: dict[UUID, SignerInfo] = {}
        for p in route.participants:
            if p.user_id is None or p.user_id in plates:
                continue
            for pair in p.assignments:
                info = await self._plates.plate_for(state, pair.slot_id, p.user_id.hex)
                if info is not None:
                    plates[p.user_id] = info
                    break
        return plates
