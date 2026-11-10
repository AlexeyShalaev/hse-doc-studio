"""«Показать» придержанную картинку (docs/design/signing-route.md, 5.6).

Маршрут придерживает картинку подписанта до его согласия (`SignaturesState.withheld`, раздел 6.1). Отмена маршрута
файлы не трогает: картинки тех, кто не согласовал, остаются придержанными, ведь отмена не согласие подписанта.
Показать такую картинку можно только явным действием того, кто правит размещения (`FILES_WRITE`, как любая правка
размещения), и только пока документ не держит идущий маршрут (`ISigningRouteGate.require_unlocked` в ручке).
Действие пишется в аудит: картинка встаёт в документ без согласия подписанта по маршруту.

Остановленный и возвращённый маршрут правку не держат: при повторной отправке расчёт снова придержит картинку
участника без действующего согласия.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
)
from hse_doc_studio.core.signatures.ports import ISignatureAudit
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class ReleaseWithheldInput:
    project_id: UUID
    doc_id: str
    slot_id: str


class ReleaseWithheldUC:
    """Снять слот документа с придержания: картинка снова видна в предпросмотре, «С подписями» и фиксации."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        audit: ISignatureAudit | None = None,
    ) -> None:
        self._signature_repo = signature_repo
        self._audit = audit
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: ReleaseWithheldInput) -> bool:
        """True, если слот был придержан и теперь показан; повтор ничего не пишет (False)."""
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        state = self._signature_repo.get_state(project.folder)
        held = state.withheld.get(inp.doc_id, frozenset())
        if inp.slot_id not in held:
            return False
        rest = held - {inp.slot_id}
        withheld = {doc_id: slots for doc_id, slots in state.withheld.items() if doc_id != inp.doc_id}
        if rest:
            withheld[inp.doc_id] = frozenset(rest)
        self._signature_repo.save_state(project.folder, replace(state, withheld=withheld))
        logger.info("withheld signature released", project_id=str(inp.project_id), doc_id=inp.doc_id, slot=inp.slot_id)
        if self._audit is not None:
            await self._audit.record(
                "signature.release", project_id=inp.project_id, details={"doc_id": inp.doc_id, "slot_id": inp.slot_id}
            )
        return True
