from __future__ import annotations

import contextlib
from dataclasses import dataclass, replace
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class DeleteDetachedSignatureInput:
    project_id: UUID
    doc_id: str
    slot_id: str


class DeleteDetachedSignatureUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
    ) -> None:
        self._signature_repo = signature_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: DeleteDetachedSignatureInput) -> None:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        state = self._signature_repo.get_state(project.folder)
        doc_sigs = dict(state.detached.get(inp.doc_id, {}))
        sig = doc_sigs.pop(inp.slot_id, None)
        if sig is None:
            raise NotFoundError(
                localized_error("К слоту не приложена подпись", "No signature is attached to this slot")
            )
        with contextlib.suppress(OSError):
            (project.folder / sig.file).unlink()
        detached = {k: v for k, v in state.detached.items() if k != inp.doc_id}
        if doc_sigs:
            detached[inp.doc_id] = doc_sigs
        self._signature_repo.save_state(project.folder, replace(state, detached=detached))
        logger.info("detached signature deleted", project_id=str(inp.project_id), doc_id=inp.doc_id, slot=inp.slot_id)
