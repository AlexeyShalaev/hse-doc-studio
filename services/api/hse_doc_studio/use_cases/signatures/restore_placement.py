"""«Вернуть место из шаблона» у слота документа (docs/design/signing-route.md, 15.6 и 15.11).

`POST .../signatures/placements/{doc_id}/{slot_id}/restore` ставит место и метки даты слота документа как в шаблоне
проекта (`placements` документа, иначе `default_placement`; `default_dates` документа) и пометку `from_pack`.
Включённость, дата в рамке и момент подписи не меняются. Размещения может ещё не быть: оно создаётся выключенным.

Место на якоре шаблона (15.17.8, 15.17.9) считается по якорям источника подписи: версии на подписи, если она есть,
иначе текущей сборки. Якоря неизвестны и запасного места нет (или источник это свой загруженный PDF): 409
`anchors_unknown`; якоря известны, а строки для подписи в документе нет: 409 `anchor_missing`.

Правила те же, что у правки меток даты (14.6): документ, который держит идущий или завершённый маршрут, правит его
сценарий (`ISigningRouteGate.edit_dates`): без права отправки маршрута 409 `route_locked`, при ЭП над зафиксированным
PDF без `confirm_reset` 409 `resets_signatures`. Повтор без изменений ничего не пишет и в аудит не попадает.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
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
from hse_doc_studio.core.signatures.pack_places import NO_ANCHORS, SourceAnchors, pack_placement
from hse_doc_studio.core.signatures.ports import ISignatureAudit
from hse_doc_studio.core.signatures.stamps import date_mark_text
from hse_doc_studio.core.signing_route.entities import RouteConflictError
from hse_doc_studio.core.signing_route.ports import ISigningRouteGate
from hse_doc_studio.core.value_objects import SignaturePlacement, SignaturesState
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.signatures._studio_signer import project_lock
from hse_doc_studio.use_cases.signatures.pack_places import MANUAL, PackPlaces, PlaceInfo
from hse_doc_studio.use_cases.signatures.set_slot_optional import unknown_slot
from hse_doc_studio.use_cases.signatures.source_anchors import doc_anchors

logger = structlog.get_logger()


@dataclass
class RestorePlacementInput:
    project_id: UUID
    doc_id: str
    slot_id: str
    # Подтверждение сброса подписей сценарием маршрута (14.6); мимо маршрута не нужно.
    confirm_reset: bool = False


@dataclass(frozen=True)
class RestorePlacementOutput:
    placement: SignaturePlacement
    # Что напечатает каждая метка даты сейчас, в порядке `placement.dates`; None у пустой.
    texts: tuple[str | None, ...]
    place: PlaceInfo = MANUAL


def anchors_unknown() -> RouteConflictError:
    return RouteConflictError(
        "anchors_unknown",
        localized_error(
            "Место из шаблона появится после сборки документа: строки шаблона пока неизвестны",
            "The template place appears after the document is built: the template lines are not known yet",
        ),
    )


def anchor_missing() -> RouteConflictError:
    return RouteConflictError(
        "anchor_missing",
        localized_error(
            "В собранном документе нет строки для этой подписи. Проверьте данные проекта или поставьте место вручную",
            "The built document has no line for this signature. Check the project data or place it manually",
        ),
    )


def _no_place(src: SourceAnchors) -> RouteConflictError:
    return anchor_missing() if src.known else anchors_unknown()


def _signatures_of(state: SignaturesState, doc_id: str) -> set[str]:
    return {*state.detached.get(doc_id, {}), *state.embedded.get(doc_id, {})}


class RestorePlacementUC:
    def __init__(  # noqa: PLR0913 — порты сценария перечислены явно
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        signature_repo: ISignatureRepository,
        template_repo: ITemplateRepository,
        routes: ISigningRouteGate,
        audit: ISignatureAudit | None = None,
        template_service: ProjectTemplateService | None = None,
    ) -> None:
        self._signature_repo = signature_repo
        self._template_repo = template_repo
        self._routes = routes
        self._audit = audit
        self._template_service = template_service
        self._slots = SignatureSlotService()
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: RestorePlacementInput) -> RestorePlacementOutput:
        project, version, doc, rslot = await self._load(inp)

        async def write(state: SignaturesState) -> SignaturesState:
            existing = state.placements.get(inp.doc_id, {}).get(inp.slot_id)
            src = await self._anchors(project, version, state, doc)
            placement = pack_placement(rslot.slot_def, doc.def_id, existing, version.version, src)
            if placement is None:
                raise _no_place(src)
            if placement == existing:
                return state
            doc_placements = {**state.placements.get(inp.doc_id, {}), inp.slot_id: placement}
            return replace(state, placements={**state.placements, inp.doc_id: doc_placements})

        before = self._signature_repo.get_state(project.folder)
        updated = await self._routes.edit_dates(
            project.id, inp.doc_id, inp.slot_id, write, manual=False, confirm_reset=inp.confirm_reset
        )
        if updated is None:
            async with project_lock(project):
                state = self._signature_repo.get_state(project.folder)
                updated = await write(state)
                if updated != state:
                    self._signature_repo.save_state(project.folder, updated)
        # `write` создаёт размещение, если его не было: после него оно есть всегда.
        placement = updated.placements[inp.doc_id][inp.slot_id]
        if placement != before.placements.get(inp.doc_id, {}).get(inp.slot_id):
            await self._record(inp, version, before, updated)
        lang = str(project.lang)
        texts = tuple(date_mark_text(updated, inp.doc_id, inp.slot_id, mark, lang) for mark in placement.dates)
        anchors = {inp.doc_id: await self._anchors(project, version, updated, doc)}
        place = PackPlaces.load(self._template_repo, project, version, anchors).info(inp.doc_id, inp.slot_id, placement)
        return RestorePlacementOutput(placement=placement, texts=texts, place=place)

    async def _anchors(
        self, project: Project, version: TemplateVersion, state: SignaturesState, doc: Document
    ) -> SourceAnchors:
        """Якоря источника подписи документа (15.17.9); без сервиса шаблонов (тесты без сборки) неизвестны."""
        if self._template_service is None:
            return SourceAnchors(own_pdf=doc.custom_file is not None) if doc.custom_file is not None else NO_ANCHORS
        return await doc_anchors(self._template_service, project, version, state, doc)

    async def _load(self, inp: RestorePlacementInput) -> tuple[Project, TemplateVersion, Document, RuntimeSlot]:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        version = self._template_repo.get_version(project.lock.pack_id, project.lock.template_id, project.lock.version)
        if version is None:
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена для проекта {inp.project_id}",
                    f"Template version not found for project {inp.project_id}",
                )
            )
        doc = next((d for d in project.documents if d.id == inp.doc_id), None)
        if doc is None:
            raise NotFoundError(
                localized_error(f"Документ {inp.doc_id!r} не найден", f"Document {inp.doc_id!r} not found")
            )
        # Места из шаблона у пары нет: слота нет в версии проекта или он не ставится на документ (400 `unknown_slot`).
        rslot = self._slots.find_runtime_slot(project, version, inp.slot_id)
        if rslot is None or not self._slots.slot_applies_to_doc(rslot, doc):
            raise unknown_slot()
        return project, version, doc, rslot

    async def _record(
        self, inp: RestorePlacementInput, version: TemplateVersion, before: SignaturesState, after: SignaturesState
    ) -> None:
        logger.info(
            "signature placement restored from the template",
            project_id=str(inp.project_id),
            doc_id=inp.doc_id,
            slot=inp.slot_id,
            version=version.version,
        )
        if self._audit is None:
            return
        reset = sorted(_signatures_of(before, inp.doc_id) - _signatures_of(after, inp.doc_id))
        details: dict[str, object] = {
            "doc_id": inp.doc_id,
            "slot_id": inp.slot_id,
            "version": version.version,
            "reset": [{"doc_id": inp.doc_id, "slot_id": slot_id} for slot_id in reset],
        }
        held = next((r for r in await self._routes.held_routes(inp.project_id) if inp.doc_id in r.docs), None)
        if held is not None:
            details["route_id"] = str(held.route_id)
        await self._audit.record("signature.placement_restore", project_id=inp.project_id, details=details)
