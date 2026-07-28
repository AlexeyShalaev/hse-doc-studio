from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
)
from hse_doc_studio.core.value_objects import SignaturePlacement, SignaturesState
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()

_PNG_DIR = ".hse-studio/signatures"


@dataclass
class DeleteSignaturePngInput:
    project_id: UUID
    slot_id: str


@dataclass
class DeleteSignaturePngOutput:
    file_existed: bool


class DeleteSignaturePngUC:
    """Removes the slot's uploaded PNG and disables every placement that used it.

    Placements (x/y/page/width) are preserved with enabled=False so a later
    re-upload restores the user's positioning. The on-disk PNG file is best-
    effort removed; a stuck file (locked, missing) doesn't block the state
    update.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
    ) -> None:
        self._signature_repo = signature_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: DeleteSignaturePngInput) -> DeleteSignaturePngOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        target_file = project.folder / _PNG_DIR / f"{inp.slot_id}.png"
        file_existed = target_file.exists()
        if file_existed:
            with suppress(OSError):
                target_file.unlink()

        state = self._signature_repo.get_state(project.folder)
        new_slots = {sid: slot for sid, slot in state.slots.items() if sid != inp.slot_id}
        new_placements: dict[str, dict[str, SignaturePlacement]] = {}
        disabled_in: list[str] = []
        for doc_id, slots in state.placements.items():
            new_doc_placements: dict[str, SignaturePlacement] = {}
            for sid, placement in slots.items():
                if sid == inp.slot_id and placement.enabled:
                    disabled_in.append(doc_id)
                    new_doc_placements[sid] = SignaturePlacement(
                        enabled=False,
                        page=placement.page,
                        x_mm=placement.x_mm,
                        y_mm=placement.y_mm,
                        width_mm=placement.width_mm,
                    )
                else:
                    new_doc_placements[sid] = placement
            new_placements[doc_id] = new_doc_placements

        new_state = SignaturesState(slots=new_slots, placements=new_placements)
        self._signature_repo.save_state(project.folder, new_state)

        logger.info(
            "signature png deleted",
            project_id=str(inp.project_id),
            slot_id=inp.slot_id,
            file_existed=file_existed,
            disabled_in_docs=disabled_in,
        )
        return DeleteSignaturePngOutput(file_existed=file_existed)
