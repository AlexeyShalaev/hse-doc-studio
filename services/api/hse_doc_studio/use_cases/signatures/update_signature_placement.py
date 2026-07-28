from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import SignatureSlotService
from hse_doc_studio.core.value_objects import SignaturePlacement, SignaturesState
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class UpdateSignaturePlacementInput:
    project_id: UUID
    doc_id: str
    slot_id: str
    enabled: bool | None = None
    page: int | None = None
    x_mm: float | None = None
    y_mm: float | None = None
    width_mm: float | None = None
    # None — не менять; пустая строка — очистить дату; иначе ISO «2026-05-12».
    sign_date: str | None = None


@dataclass
class UpdateSignaturePlacementOutput:
    placement: SignaturePlacement


class UpdateSignaturePlacementUC:
    """Partial update for a single (doc, slot) placement cell.

    Any field left as None falls back to the existing stored value; if no
    placement existed for this (doc, slot) yet, we seed it from the template
    slot's default_placement. Position is independent across docs — the same
    slot can sit on page 1 of vkr and page 2 of tz.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._slot_service = SignatureSlotService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UpdateSignaturePlacementInput) -> UpdateSignaturePlacementOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена для проекта {inp.project_id}",
                    f"Template version not found for project {inp.project_id}",
                )
            )

        # Рантайм-слоты: в team per-author слоты пака размножены в
        # "{slot}--{slug}"; применимость считается по def_id и владельцу.
        rslot = self._slot_service.find_runtime_slot(project, version, inp.slot_id)
        if rslot is None:
            raise NotFoundError(
                localized_error(
                    f"Слот {inp.slot_id!r} не определён в шаблоне {project.lock.pack_id}/{project.lock.template_id}",
                    f"Slot {inp.slot_id!r} is not defined in template "
                    f"{project.lock.pack_id}/{project.lock.template_id}",
                )
            )

        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(
                    f"Документ {inp.doc_id!r} не найден в проекте {inp.project_id}",
                    f"Document {inp.doc_id!r} not found in project {inp.project_id}",
                )
            )
        if not self._slot_service.slot_applies_to_doc(rslot, doc):
            raise ValueError(
                localized_error(
                    f"Слот {inp.slot_id!r} не применим к документу {inp.doc_id!r}",
                    f"Slot {inp.slot_id!r} does not apply to document {inp.doc_id!r}",
                )
            )
        slot_def = rslot.slot_def

        state = self._signature_repo.get_state(project.folder)
        doc_placements = dict(state.placements.get(inp.doc_id, {}))
        existing = doc_placements.get(inp.slot_id)

        default = slot_def.default_placement
        enabled = inp.enabled if inp.enabled is not None else (existing.enabled if existing else False)
        page = inp.page if inp.page is not None else (existing.page if existing else default.page)
        x_mm = inp.x_mm if inp.x_mm is not None else (existing.x_mm if existing else default.x_mm)
        y_mm = inp.y_mm if inp.y_mm is not None else (existing.y_mm if existing else default.y_mm)
        width_mm = inp.width_mm if inp.width_mm is not None else (existing.width_mm if existing else default.width_mm)
        # None — не менять; "" — очистить дату; иначе новое значение.
        kept_date = existing.sign_date if existing else None
        sign_date = kept_date if inp.sign_date is None else (inp.sign_date or None)

        new_placement = SignaturePlacement(
            enabled=enabled,
            page=page,
            x_mm=x_mm,
            y_mm=y_mm,
            width_mm=width_mm,
            sign_date=sign_date,
        )
        doc_placements[inp.slot_id] = new_placement

        new_state = SignaturesState(
            slots=dict(state.slots),
            placements={**state.placements, inp.doc_id: doc_placements},
        )
        self._signature_repo.save_state(project.folder, new_state)

        logger.info(
            "signature placement updated",
            project_id=str(inp.project_id),
            doc_id=inp.doc_id,
            slot_id=inp.slot_id,
            enabled=enabled,
        )
        return UpdateSignaturePlacementOutput(placement=new_placement)
