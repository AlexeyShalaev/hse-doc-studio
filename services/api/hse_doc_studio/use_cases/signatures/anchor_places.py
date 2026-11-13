"""Пересчёт мест подписей на якорях шаблона после сборки (docs/design/signing-route.md, 15.17.9).

Состояние подписей хранит места в мм; якоря только источник, из которого Студия вычисляет место «из шаблона». После
публикации сборки места документа, которые Студия поставила по записи пака на якоре и которые человек не трогал
(`from_pack`, отпечаток совпадает), встают по якорям этой сборки; якоря нет, и место выключается, чтобы картинка не
легла на чужую строку. На сервере ещё пары черновиков маршрута на документе без места или с затравкой получают место
пресета, как при создании черновика (`IRouteDraftPlaces`).

Пересчёта нет, если источник подписи не эта сборка (есть версия на подписи), документ держит маршрут, над B есть ЭП,
источник это свой загруженный PDF или якоря сборки неизвестны. Ручные места не трогаются никогда. Запись в
`signatures.json` только при изменении; аудит пересчёт не пишет, итог виден в записи сборки.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import SignatureSlotDef, TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.repositories import IProjectRepository, ISignatureRepository, ITemplateRepository
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.pack_places import SourceAnchors, is_from_pack, pack_placement, placement_digest
from hse_doc_studio.core.signatures.plan import VisibleMark, mark_of
from hse_doc_studio.core.signatures.ports import IRouteDraftPlaces, NoRouteDraftPlaces
from hse_doc_studio.core.signatures.stamps import widen_for_plate
from hse_doc_studio.core.team import is_team, split_instance_id
from hse_doc_studio.core.value_objects import SignaturePlacement, SignaturesState
from hse_doc_studio.use_cases.signatures._studio_signer import project_lock
from hse_doc_studio.use_cases.signatures.source_anchors import doc_anchors

logger = structlog.get_logger()


def _slot_def(version: TemplateVersion, project: Project, doc: Document, slot_id: str) -> SignatureSlotDef | None:
    """Слот каталога версии для рантайм-слота на документе; None, если пак место этой пары не ставит.

    Экземпляр автора (`author--<слаг>`) на общем документе команды места из пака не получает (15.5).
    """
    base_id, owner = split_instance_id(slot_id)
    slot_def = next((s for s in version.signatures_config.slots if s.id == base_id), None)
    if slot_def is None or doc.def_id not in slot_def.applies_to:
        return None
    if is_team(project) and slot_def.per_author and doc.owner is None:
        return None
    if owner is not None and doc.owner is None:
        return None
    return slot_def


def rebuilt_place(
    slot_def: SignatureSlotDef, doc_def_id: str, placement: SignaturePlacement, version: str, src: SourceAnchors
) -> SignaturePlacement | None:
    """Место из шаблона на якоре по якорям сборки `src`; None, если место не пересчитывается (ручное, в мм, якоря
    неизвестны) или не меняется. Якоря нет (или рамка за краем листа): прежняя геометрия, место выключено.

    Только сборка (`from_pack.build`) без сдвига линии место не меняет: запись в `signatures.json` только при
    изменении геометрии, меток или включённости, иначе git-синхронизация получала бы запись на каждую сборку.
    """
    if not src.known or not is_from_pack(placement) or not slot_def.uses_anchors(doc_def_id):
        return None
    moved = pack_placement(slot_def, doc_def_id, placement, version, src)
    if moved is None:
        moved = replace(placement, enabled=False)
    if moved.enabled == placement.enabled and placement_digest(moved) == placement_digest(placement):
        return None
    return moved


def rebuild_places(
    state: SignaturesState, project: Project, version: TemplateVersion, doc: Document, src: SourceAnchors
) -> SignaturesState:
    """Места документа «из шаблона» на якоре по якорям сборки (`rebuilt_place`); плашка открепленной ЭП расширяет
    рамку, как у любого места (`widen_for_plate`, 6.3)."""
    current = state.placements.get(doc.id, {})
    changed: dict[str, SignaturePlacement] = {}
    for slot_id, placement in current.items():
        slot_def = _slot_def(version, project, doc, slot_id)
        if slot_def is None:
            continue
        moved = rebuilt_place(slot_def, doc.def_id, placement, version.version, src)
        if moved is not None and moved != placement:
            changed[slot_id] = moved
    if not changed:
        return state
    updated = replace(state, placements={**state.placements, doc.id: {**current, **changed}})
    plates = [(doc.id, slot_id) for slot_id in changed if mark_of(state.slots.get(slot_id)) is VisibleMark.plate]
    return widen_for_plate(updated, plates) if plates else updated


def moved_count(before: SignaturesState, after: SignaturesState, doc_id: str) -> int:
    """Сколько размещений документа изменилось."""
    old, new = before.placements.get(doc_id, {}), after.placements.get(doc_id, {})
    return sum(1 for slot_id, placement in new.items() if old.get(slot_id) != placement)


def _signed_over_frozen(state: SignaturesState, doc_id: str) -> bool:
    return doc_id in state.frozen and bool(state.detached.get(doc_id) or state.embedded.get(doc_id))


class BuildPlaces:
    """`IBuildPlaces`: пересчёт мест на якорях после публикации сборки, под `project_lock` проекта."""

    def __init__(  # noqa: PLR0913 — порты перечислены явно
        self,
        project_repo: IProjectRepository,
        template_repo: ITemplateRepository,
        signature_repo: ISignatureRepository,
        template_service: ProjectTemplateService | None = None,
        routes: IRouteDraftPlaces | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._template_repo = template_repo
        self._signature_repo = signature_repo
        self._template_service = template_service or ProjectTemplateService()
        self._routes = routes or NoRouteDraftPlaces()

    async def after_build(self, project_id: UUID, folder: Path, doc_id: str) -> int:
        project = self._project_repo.get(folder)
        found = self._target(project, doc_id) if project is not None else None
        if project is None or found is None:
            return 0
        version, doc = found
        async with project_lock(project):
            state = self._signature_repo.get_state(folder)
            updated = await self._rebuilt(project_id, project, version, doc, state)
            if updated is None or updated == state:
                return 0
            self._signature_repo.save_state(folder, updated)
        moved = moved_count(state, updated, doc_id)
        logger.info("signature places follow the template lines", project_id=str(project_id), doc_id=doc_id, n=moved)
        return moved

    def _target(self, project: Project, doc_id: str) -> tuple[TemplateVersion, Document] | None:
        """Версия шаблона и документ, у которого бывают строки шаблона; свой загруженный PDF их не имеет."""
        lock = project.lock
        version = self._template_repo.get_version(lock.pack_id, lock.template_id, lock.version)
        doc = next((d for d in project.documents if d.id == doc_id), None)
        if version is None or doc is None or doc.custom_file is not None:
            return None
        return version, doc

    async def _rebuilt(
        self, project_id: UUID, project: Project, version: TemplateVersion, doc: Document, state: SignaturesState
    ) -> SignaturesState | None:
        """Состояние после пересчёта; None, если пересчёта нет (версия на подписи, ЭП над B, якоря неизвестны,
        документ держит маршрут)."""
        if doc.id in state.pinned or _signed_over_frozen(state, doc.id):
            return None
        src = await doc_anchors(self._template_service, project, version, state, doc)
        if not src.known:
            return None
        routed = await self._routes.apply(project_id, doc.id, state, src)
        return rebuild_places(routed, project, version, doc, src) if routed is not None else None
