from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import SignatureDefaultPlacement
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import RuntimeSlot, SignatureSlotService
from hse_doc_studio.core.value_objects import (
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
)
from hse_doc_studio.infra.signatures.png_metadata import is_png, read_dimensions_from_bytes
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

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
    a default placement (enabled=False) for each applicable document so the
    UI has something to render right away; existing placements are preserved.
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

    def _seed_default_placements(
        self,
        placements: dict[str, dict[str, SignaturePlacement]],
        project: Project,
        rslot: RuntimeSlot,
        slot_id: str,
        default: SignatureDefaultPlacement,
    ) -> None:
        for doc in project.documents:
            if not self._slot_service.slot_applies_to_doc(rslot, doc):
                continue
            doc_placements = placements.setdefault(doc.id, {})
            if slot_id not in doc_placements:
                doc_placements[slot_id] = SignaturePlacement(
                    enabled=False,
                    page=default.page,
                    x_mm=default.x_mm,
                    y_mm=default.y_mm,
                    width_mm=default.width_mm,
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
        slot_def = rslot.slot_def

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
        new_slots[inp.slot_id] = SignatureSlot(
            png_path=relative_path,
            natural_width_px=natural_w,
            natural_height_px=natural_h,
        )

        # Сеем дефолтные размещения по ИНСТАНСАМ документов, к которым слот
        # применим (`applies_to` пака — id определений; в team инстансов
        # больше: личные доки владельца + общие).
        new_placements = {doc_id: dict(slots) for doc_id, slots in state.placements.items()}
        self._seed_default_placements(new_placements, project, rslot, inp.slot_id, slot_def.default_placement)

        new_state = SignaturesState(slots=new_slots, placements=new_placements)
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
