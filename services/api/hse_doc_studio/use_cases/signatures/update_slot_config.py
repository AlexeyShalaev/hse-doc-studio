from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ISigningIdentityRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import SignatureSlotService
from hse_doc_studio.core.value_objects import SignatureSlot, SignaturesState
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class UpdateSlotConfigInput:
    project_id: UUID
    slot_id: str
    signing_identity_id: str | None  # None = clear
    sign_mode: SignMode
    sign_reason: str = ""


@dataclass
class UpdateSlotConfigOutput:
    slot: SignatureSlot


class UpdateSlotConfigUC:
    """Assign or clear a signing identity on a signature slot.

    Validates that the slot_id exists in the template and, when setting an
    identity, that the identity exists in the local registry. Does NOT touch
    placements — only the slot-level crypto config.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        signing_identity_repo: ISigningIdentityRepository,
        template_repo: ITemplateRepository,
    ) -> None:
        self._signature_repo = signature_repo
        self._signing_identity_repo = signing_identity_repo
        self._template_repo = template_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UpdateSlotConfigInput) -> UpdateSlotConfigOutput:
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

        if SignatureSlotService().find_runtime_slot(project, version, inp.slot_id) is None:
            raise NotFoundError(
                localized_error(
                    f"Слот {inp.slot_id!r} не определён в шаблоне {project.lock.pack_id}/{project.lock.template_id}",
                    f"Slot {inp.slot_id!r} is not defined in template "
                    f"{project.lock.pack_id}/{project.lock.template_id}",
                )
            )

        if inp.signing_identity_id is not None:
            identity = self._signing_identity_repo.get(UUID(inp.signing_identity_id))
            if identity is None:
                raise NotFoundError(
                    localized_error(
                        f"Учётная запись подписи {inp.signing_identity_id!r} не найдена",
                        f"Signing identity {inp.signing_identity_id!r} not found",
                    )
                )

        state = self._signature_repo.get_state(project.folder)
        existing = state.slots.get(inp.slot_id)

        new_slot = SignatureSlot(
            png_path=existing.png_path if existing else None,
            natural_width_px=existing.natural_width_px if existing else None,
            natural_height_px=existing.natural_height_px if existing else None,
            signing_identity_id=inp.signing_identity_id,
            sign_mode=inp.sign_mode if inp.signing_identity_id else SignMode.image,
            # Reason only carries meaning for crypto modes; cleared with identity.
            sign_reason=inp.sign_reason if inp.signing_identity_id else "",
        )
        new_slots = dict(state.slots)
        new_slots[inp.slot_id] = new_slot
        new_state = SignaturesState(slots=new_slots, placements=state.placements)
        self._signature_repo.save_state(project.folder, new_state)

        logger.info(
            "slot config updated",
            project_id=str(inp.project_id),
            slot_id=inp.slot_id,
            identity=inp.signing_identity_id,
            mode=inp.sign_mode.value,
        )
        return UpdateSlotConfigOutput(slot=new_slot)
