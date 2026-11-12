from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService, RuntimeSlot, SignatureSlotService
from hse_doc_studio.core.signatures.stamps import stamps_digest_matches, stamps_for_doc
from hse_doc_studio.core.signing_route.ports import HeldRoute, ISigningRouteGate
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures.signing_source import source_of

logger = structlog.get_logger()


@dataclass
class GetSignaturesInput:
    project_id: UUID


@dataclass
class ProfileRef:
    """Контрольная точка, требующая подпись: id и локализованное название."""

    id: str
    name: dict[str, str]


@dataclass
class RuntimeSlotItem:
    """Рантайм-слот с применимостью, посчитанной на уровне ИНСТАНСОВ доков."""

    slot: RuntimeSlot
    applies_to: list[str]
    # Где подпись ОБЯЗАТЕЛЬНА и на какой точке: id инстанса документа →
    # контрольные точки. Пустая запись = слот применим, но ни одним комплектом
    # не требуется (например, со-руководитель, которого у работы нет).
    required_by: dict[str, list[ProfileRef]]
    # Точки, чей маршрут включил слот в документ сверх точки (`extra_slots`): id инстанса документа → точки
    # (signing-route.md, 13.6). Там автор тоже может отметить подпись необязательной.
    extra_by: dict[str, list[ProfileRef]] = field(default_factory=dict)


@dataclass
class GetSignaturesOutput:
    state: SignaturesState
    runtime_slots: list[RuntimeSlotItem]
    # Docs whose signing source (the version sent for signing, else the build) changed after freezing.
    stale_frozen: set[str] = field(default_factory=set)
    # Docs whose signature plates or positions changed after the PDF was frozen.
    plate_outdated: set[str] = field(default_factory=set)


class GetSignaturesUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService | None = None,
        routes: ISigningRouteGate | None = None,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._routes = routes
        self._slot_service = SignatureSlotService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetSignaturesInput) -> GetSignaturesOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        state = self._signature_repo.get_state(project.folder)

        # Рантайм-слоты проекта (team: per-author размножение) с применимостью
        # по инстансам — фронтенд рендерит панели подписей по ним, а не по
        # каталогу пака, у которого applies_to ссылается на id определений.
        runtime_slots: list[RuntimeSlotItem] = []
        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is not None:
            # Обязательность подписи выводится из профилей сдачи: она свойство
            # пары «документ + контрольная точка», а не документа.
            required = self._slot_service.required_by_profiles(project, version)
            profile_names = {
                p.id: dict(p.name)
                for p in (version.pack_submission.profiles if version.pack_submission is not None else ())
            }
            held = await self._routes.held_routes(project.id) if self._routes is not None else ()
            extra = _extra_by(held, required)
            runtime_slots = [
                RuntimeSlotItem(
                    slot=slot,
                    applies_to=[d.id for d in project.documents if self._slot_service.slot_applies_to_doc(slot, d)],
                    required_by={
                        doc_id: [ProfileRef(id=pid, name=profile_names.get(pid, {"ru": pid})) for pid in profile_ids]
                        for doc_id, profile_ids in required.get(slot.id, {}).items()
                    },
                    extra_by={
                        doc_id: [ProfileRef(id=pid, name=profile_names.get(pid, {"ru": pid})) for pid in profile_ids]
                        for doc_id, profile_ids in extra.get(slot.id, {}).items()
                    },
                )
                for slot in self._slot_service.runtime_slots(project, version)
            ]

        stale, outdated = await self._frozen_flags(project, version, state)

        return GetSignaturesOutput(
            state=state, runtime_slots=runtime_slots, stale_frozen=stale, plate_outdated=outdated
        )

    async def _frozen_flags(  # noqa: C901
        self, project: Project, version: TemplateVersion | None, state: SignaturesState
    ) -> tuple[set[str], set[str]]:
        """(docs rebuilt since freezing, docs whose plates or positions changed since freezing)."""
        stale: set[str] = set()
        outdated: set[str] = set()
        for doc_id, frozen in state.frozen.items():
            current = stamps_for_doc(state, doc_id, project.folder, str(project.lang))
            if not stamps_digest_matches(frozen.stamps_digest, current, project.folder):
                outdated.add(doc_id)
        if version is None or self._template_service is None:
            return stale, outdated
        for doc_id, frozen in state.frozen.items():
            doc = next((d for d in project.documents if d.id == doc_id), None)
            if doc is None:
                continue
            try:
                _, output_file = self._template_service.resolve_instance_source(project, doc, version)
            except NotFoundError:
                continue
            # Сверка с источником подписи: версией на подписи маршрута, иначе текущей сборкой (signing-route.md, 12.4).
            source = await source_of(project.folder, project.folder / output_file, state, doc_id)
            if source.sha256 is not None and source.sha256 != frozen.source_sha256:
                stale.add(doc_id)
        return stale, outdated


def _extra_by(
    routes: tuple[HeldRoute, ...], required: dict[str, dict[str, tuple[str, ...]]]
) -> dict[str, dict[str, list[str]]]:
    """Слот → документ → точки, чей маршрут включил пару, хотя сама точка её не требует (`extra_slots`)."""
    result: dict[str, dict[str, list[str]]] = {}
    for route in routes:
        for doc_id, slot_id in sorted(route.pairs):
            if route.profile_id in required.get(slot_id, {}).get(doc_id, ()):
                continue
            points = result.setdefault(slot_id, {}).setdefault(doc_id, [])
            if route.profile_id not in points:
                points.append(route.profile_id)
    return result
