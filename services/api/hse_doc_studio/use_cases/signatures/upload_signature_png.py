from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import AnchorPlace, TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService, RuntimeSlot, SignatureSlotService
from hse_doc_studio.core.signatures.pack_places import pack_placement, stamp_from_pack
from hse_doc_studio.core.value_objects import (
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
)
from hse_doc_studio.infra.signatures.png_metadata import is_png, read_dimensions_from_bytes
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures.source_anchors import doc_anchors

logger = structlog.get_logger()

_PNG_DIR = ".hse-studio/signatures"


@dataclass
class UploadSignaturePngInput:
    project_id: UUID
    slot_id: str
    filename: str
    content: bytes


@dataclass
class UploadSignaturePngOutput:
    png_path: str
    natural_width_px: int | None
    natural_height_px: int | None


class UploadSignaturePngUC:
    """Saves an uploaded PNG to the project's signatures folder.

    The PNG is stored once per slot — the same file is reused across every
    document the slot applies to. On first upload for a slot we also seed
    a placement (enabled=False) for each applicable document at the pack's place
    for that document (`placements`, else `default_placement`, signing-route.md, 15.3)
    so the UI has something to render right away; existing placements are preserved.
    Seeds carry no `from_pack` mark: they are recognised by geometry (15.4). A seed of an anchored pack place
    (15.17.9) is computed from the anchors of the document's signing source and always carries the mark: its
    millimetres change from build to build; with the anchors unknown it takes the fallback place, if any.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService | None = None,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._template_service = template_service
        self._slot_service = SignatureSlotService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def _seed_default_placements(  # noqa: PLR0913 — что посеять и где
        self,
        placements: dict[str, dict[str, SignaturePlacement]],
        project: Project,
        version: TemplateVersion,
        state: SignaturesState,
        rslot: RuntimeSlot,
        slot_id: str,
    ) -> None:
        for doc in project.documents:
            if not self._slot_service.slot_applies_to_doc(rslot, doc):
                continue
            doc_placements = placements.setdefault(doc.id, {})
            if slot_id in doc_placements:
                continue
            seeded = await self._anchored_seed(project, version, state, rslot, doc)
            if seeded is not None:
                doc_placements[slot_id] = seeded
                continue
            default = rslot.slot_def.place_for(doc.def_id)
            doc_placements[slot_id] = SignaturePlacement(
                enabled=False,
                page=default.page,
                x_mm=default.x_mm,
                y_mm=default.y_mm,
                width_mm=default.width_mm,
            )

    async def _anchored_seed(
        self, project: Project, version: TemplateVersion, state: SignaturesState, rslot: RuntimeSlot, doc: Document
    ) -> SignaturePlacement | None:
        """Затравка места на якоре с пометкой (15.17.10), без меток даты: их ставит только пресет; None, если место
        не на якоре или его нет (тогда затравка в мм без пометки, как раньше)."""
        if self._template_service is None or not isinstance(rslot.slot_def.entry_for(doc.def_id), AnchorPlace):
            return None
        src = await doc_anchors(self._template_service, project, version, state, doc)
        placement = pack_placement(rslot.slot_def, doc.def_id, None, version.version, src)
        if placement is None:
            return None
        return stamp_from_pack(
            replace(placement, dates=()),
            version.version,
            anchor=placement.from_pack.anchor if placement.from_pack else None,
            build=placement.from_pack.build if placement.from_pack else None,
        )

    async def execute(self, inp: UploadSignaturePngInput) -> UploadSignaturePngOutput:
        if not inp.content:
            raise ValueError(localized_error("Загружен пустой файл", "Empty file upload"))
        if not is_png(inp.content):
            raise ValueError(localized_error("Загруженный файл не является PNG", "Uploaded file is not a PNG"))

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

        rslot = self._slot_service.find_runtime_slot(project, version, inp.slot_id)
        if rslot is None:
            raise NotFoundError(
                localized_error(
                    f"Слот {inp.slot_id!r} не определён в шаблоне {project.lock.pack_id}/{project.lock.template_id}",
                    f"Slot {inp.slot_id!r} is not defined in template "
                    f"{project.lock.pack_id}/{project.lock.template_id}",
                )
            )

        target_dir = project.folder / _PNG_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / f"{inp.slot_id}.png"
        target_file.write_bytes(inp.content)

        relative_path = str(PurePosixPath(_PNG_DIR) / f"{inp.slot_id}.png")
        dims = read_dimensions_from_bytes(inp.content)
        natural_w = dims[0] if dims else None
        natural_h = dims[1] if dims else None

        state = self._signature_repo.get_state(project.folder)
        new_slots = dict(state.slots)
        previous = state.slots.get(inp.slot_id)
        new_slots[inp.slot_id] = (
            replace(previous, png_path=relative_path, natural_width_px=natural_w, natural_height_px=natural_h)
            if previous is not None
            else SignatureSlot(png_path=relative_path, natural_width_px=natural_w, natural_height_px=natural_h)
        )

        # Сеем дефолтные размещения по ИНСТАНСАМ документов, к которым слот
        # применим (`applies_to` пака — id определений; в team инстансов
        # больше: личные доки владельца + общие).
        new_placements = {doc_id: dict(slots) for doc_id, slots in state.placements.items()}
        await self._seed_default_placements(new_placements, project, version, state, rslot, inp.slot_id)

        new_state = replace(state, slots=new_slots, placements=new_placements)
        self._signature_repo.save_state(project.folder, new_state)

        logger.info(
            "signature png uploaded",
            project_id=str(inp.project_id),
            slot_id=inp.slot_id,
            path=relative_path,
            natural_width_px=natural_w,
            natural_height_px=natural_h,
        )
        return UploadSignaturePngOutput(
            png_path=relative_path,
            natural_width_px=natural_w,
            natural_height_px=natural_h,
        )
