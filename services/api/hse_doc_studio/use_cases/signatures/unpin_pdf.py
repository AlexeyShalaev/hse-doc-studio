"""«Подписывать текущую сборку»: снять с документа версию на подписи (docs/design/signing-route.md, 12.4).

После снятия источник подписи документа снова текущая сборка. Зафиксированный PDF и подписи над ним остаются в
состоянии подписей, как при отмене маршрута: если рабочая сборка другая, план покажет их устаревшими (`rebuilt`).
Пока документ держит маршрут (`HOLDING_STATUSES`), снимать нельзя: 409 `route_locked`. В локальной Студии
маршрутов нет, и снять можно всегда (интерфейс предупреждает, что серверный маршрут остановится).
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, replace
from uuid import UUID

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ISignatureRepository
from hse_doc_studio.core.signatures.ports import ISignatureAudit
from hse_doc_studio.core.signing_route.ports import ISigningRouteGate
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures._studio_signer import project_lock
from hse_doc_studio.use_cases.signatures.signing_source import pinned_file

logger = structlog.get_logger()


@dataclass
class UnpinPdfInput:
    project_id: UUID
    doc_id: str


class UnpinPdfUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        routes: ISigningRouteGate,
        audit: ISignatureAudit | None = None,
    ) -> None:
        self._signature_repo = signature_repo
        self._routes = routes
        self._audit = audit
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UnpinPdfInput) -> None:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        folder = project.folder
        # Под замком проекта: сценарий маршрута пишет версию на подписи под тем же замком (12.3).
        async with project_lock(project):
            await self._routes.require_not_held(project.id, inp.doc_id)
            state = self._signature_repo.get_state(folder)
            pinned = state.pinned.get(inp.doc_id)
            if pinned is None:
                raise NotFoundError(
                    localized_error(
                        "У документа нет версии на подписи: он и так подписывается по текущей сборке",
                        "The document has no version sent for signing: it is signed from the current build already",
                    )
                )
            self._signature_repo.save_state(
                folder, replace(state, pinned={k: v for k, v in state.pinned.items() if k != inp.doc_id})
            )
            # Файл после записи состояния: не удалось удалить, лишний файл в `frozen` ничего не значит.
            path = pinned_file(folder, pinned)
            if path is not None:
                with contextlib.suppress(OSError):
                    path.unlink()
        logger.info("signing version unpinned", project_id=str(inp.project_id), doc_id=inp.doc_id)
        if self._audit is not None:
            await self._audit.record(
                "signature.unpin",
                project_id=inp.project_id,
                details={"doc_id": inp.doc_id, "sha256": pinned.sha256},
            )
