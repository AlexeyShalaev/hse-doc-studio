from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import RuntimeSlot, SignatureSlotService
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

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


@dataclass
class GetSignaturesOutput:
    state: SignaturesState
    runtime_slots: list[RuntimeSlotItem]


class GetSignaturesUC:
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
            runtime_slots = [
                RuntimeSlotItem(
                    slot=slot,
                    applies_to=[d.id for d in project.documents if self._slot_service.slot_applies_to_doc(slot, d)],
                    required_by={
                        doc_id: [ProfileRef(id=pid, name=profile_names.get(pid, {"ru": pid})) for pid in profile_ids]
                        for doc_id, profile_ids in required.get(slot.id, {}).items()
                    },
                )
                for slot in self._slot_service.runtime_slots(project, version)
            ]

        return GetSignaturesOutput(state=state, runtime_slots=runtime_slots)
