"""Точка сдачи глазами маршрута: проект, версия, профиль, пары «документ, слот» и названия.

Пары точки те же, что у плана подписей профиля (`profile_pairs` без автора: в команде это личные документы всех
ведомых авторов и общие, раздел 6.4). Необязательные пары это слоты, которые применимы к документу маршрута,
но точка их не требует (академрук на заявлении в КП): автор включает их сам.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.catalog import SubmissionProfile, TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.services import (
    ProjectTemplateService,
    RuntimeSlot,
    SignatureSlotService,
    SubmissionProfileService,
)
from hse_doc_studio.core.signatures.plan import SignMethod
from hse_doc_studio.core.signing_route.entities import DocSlot
from hse_doc_studio.core.team import is_doc_active
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures.get_signature_plan import profile_pairs

ALL_METHODS: tuple[str, ...] = tuple(m.value for m in SignMethod)


@dataclass(frozen=True)
class RoutePoint:
    project: Project
    version: TemplateVersion
    profile: SubmissionProfile
    # Пары, которые требует точка, в порядке профиля; способы, которые она разрешает (пусто: любой).
    required: tuple[DocSlot, ...]
    allowed: Mapping[DocSlot, tuple[str, ...]]
    runtime: Mapping[str, RuntimeSlot]
    documents: Mapping[str, Document]
    doc_names: Mapping[str, dict[str, str]]

    @property
    def project_id(self) -> UUID:
        return self.project.id

    def order(self, doc_ids: Iterable[str]) -> tuple[str, ...]:
        """Документы в порядке проекта, без повторов."""
        wanted = set(doc_ids)
        return tuple(doc.id for doc in self.project.documents if doc.id in wanted)

    def docs_of(self, pairs: Iterable[DocSlot]) -> tuple[str, ...]:
        return self.order(pair.doc_id for pair in pairs)

    def is_optional(self, pair: DocSlot) -> bool:
        """Слот применим к документу точки, но точка его не требует: автор включает его сам."""
        slot = self.runtime.get(pair.slot_id)
        doc = self.documents.get(pair.doc_id)
        if slot is None or doc is None or pair in self.allowed:
            return False
        return pair.doc_id in self.docs_of(self.required) and SignatureSlotService().slot_applies_to_doc(slot, doc)

    def optional_pairs(self) -> tuple[DocSlot, ...]:
        """Необязательные пары точки: слоты, применимые к её документам, которых она не требует."""
        docs = self.docs_of(self.required)
        return tuple(
            DocSlot(doc_id, slot_id)
            for doc_id in docs
            for slot_id in self.runtime
            if self.is_optional(DocSlot(doc_id, slot_id))
        )

    def doc_name(self, doc_id: str) -> dict[str, str]:
        return dict(self.doc_names.get(doc_id) or {"ru": doc_id, "en": doc_id})

    def slot_label(self, slot_id: str) -> dict[str, str]:
        slot = self.runtime.get(slot_id)
        return dict(slot.label) if slot is not None else {"ru": slot_id, "en": slot_id}

    def profile_name(self, profile_id: str) -> dict[str, str]:
        """Название контрольной точки того же пака (другой маршрут проекта); неизвестная называется своим id."""
        if profile_id == self.profile.id:
            return dict(self.profile.name)
        profile = (
            SubmissionProfileService().get_profile(self.version, profile_id)
            if self.version.pack_submission is not None
            else None
        )
        return dict(profile.name) if profile is not None else {"ru": profile_id, "en": profile_id}

    def methods(self, pairs: Iterable[DocSlot]) -> tuple[str, ...]:
        """Способы, которые точка разрешает для всех этих пар (пересечение; без ограничений любой)."""
        allowed = set(ALL_METHODS)
        for pair in pairs:
            restriction = self.allowed.get(pair, ())
            if restriction:
                allowed &= set(restriction)
        return tuple(m for m in ALL_METHODS if m in allowed)


class RoutePointLoader:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
    ) -> None:
        self._get = GetProjectUC(project_repo, project_index_repo)
        self._templates = template_repo
        self._template_service = template_service

    @property
    def template_service(self) -> ProjectTemplateService:
        return self._template_service

    async def project(self, project_id: UUID) -> Project:
        return (await self._get.execute(GetProjectInput(project_id=project_id))).project

    async def load(self, project_id: UUID, profile_id: str) -> RoutePoint:
        """Точка сдачи проекта; неизвестная точка и версия шаблона дают 404."""
        project = await self.project(project_id)
        version = self._templates.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        profile = (
            SubmissionProfileService().get_profile(version, profile_id)
            if version is not None and version.pack_submission is not None
            else None
        )
        if version is None or profile is None:
            raise NotFoundError(
                localized_error(f"Контрольная точка {profile_id!r} не найдена", f"Checkpoint {profile_id!r} not found")
            )
        pairs = profile_pairs(project, version, profile, None)
        documents = {doc.id: doc for doc in project.documents if is_doc_active(project, doc)}
        return RoutePoint(
            project=project,
            version=version,
            profile=profile,
            required=tuple(DocSlot(p.doc.id, p.slot_id) for p in pairs),
            allowed={DocSlot(p.doc.id, p.slot_id): tuple(p.allowed) for p in pairs},
            runtime={slot.id: slot for slot in SignatureSlotService().runtime_slots(project, version)},
            documents=documents,
            doc_names={
                doc_id: doc_display_name(self._template_service, version, doc) for doc_id, doc in documents.items()
            },
        )


def doc_display_name(
    template_service: ProjectTemplateService, version: TemplateVersion, doc: Document
) -> dict[str, str]:
    """Название документа `{ru, en}` из пака; у личного документа команды с владельцем в скобках."""
    definition = template_service.find_definition(version, doc)
    name = dict(definition.name) if definition is not None else {"ru": doc.id, "en": doc.id}
    if doc.owner:
        return {lang: f"{text} ({doc.owner})" for lang, text in name.items()}
    return name
