"""Пункт плана обновления `signature_presets`: места подписей из шаблона на новой версии (signing-route.md, 15.9).

Сводит чистые правила `core/template_update/signature_presets` с версиями шаблона проекта: происхождение места
(`PackPlaces`: как в шаблоне, затравка этой или более ранней версии, ручное) и место слота документа в новой версии.

Место новой версии на якоре (15.17.10) считается по якорям текущей сборки документа. Якоря неизвестны: место
остаётся, пометка новая, пункт `after_build`, если запись пака у пары изменилась; свой загруженный PDF: пара в план
не входит (место на якоре там ставит человек).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from hse_doc_studio.core.catalog import SignatureSlotDef, TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import PlacementOrigin
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.signatures.pack_places import NO_ANCHORS, SourceAnchors, pack_digest, placement_digest
from hse_doc_studio.core.signatures.plan import VisibleMark, mark_of
from hse_doc_studio.core.signing_route.ports import ISigningRouteGate
from hse_doc_studio.core.team import split_instance_id
from hse_doc_studio.core.template_update.signature_presets import (
    PresetKept,
    PresetPlace,
    SignaturePresetsPlan,
    kept_reason,
    pack_place,
    signed_docs,
    widened,
)
from hse_doc_studio.core.value_objects import SignaturePlacement, SignaturesState
from hse_doc_studio.use_cases.signatures.pack_places import PackPlaces


def _slot_def(version: TemplateVersion, base_id: str, doc_def_id: str) -> SignatureSlotDef | None:
    """Слот каталога версии, если он есть и применим к документу."""
    slot_def = next((s for s in version.signatures_config.slots if s.id == base_id), None)
    return slot_def if slot_def is not None and doc_def_id in slot_def.applies_to else None


class _Presets:
    """Сравнение мест проекта с пресетом новой версии шаблона: одна пара «документ, слот» за раз."""

    def __init__(  # noqa: PLR0913 — версии, состояние и маршруты перечислены явно
        self,
        templates: ITemplateRepository,
        project: Project,
        current: TemplateVersion,
        target: TemplateVersion,
        state: SignaturesState,
        held_docs: Iterable[str],
        anchors: Mapping[str, SourceAnchors] | None = None,
    ) -> None:
        self._anchors = dict(anchors or {})
        self._places = PackPlaces.load(templates, project, current)
        self._docs = {doc.id: doc for doc in project.documents}
        self._current = current
        self._target = target
        self._state = state
        self._held = frozenset(held_docs)
        self._signed = signed_docs(state)

    def outcome(
        self, doc_id: str, slot_id: str, placement: SignaturePlacement
    ) -> tuple[SignaturePlacement, bool] | PresetKept | None:
        """Новое место пары и `after_build`, причина оставить её как есть или None, если пары в пункте плана нет."""
        found = self._target_of(doc_id, slot_id)
        if found is None:
            return None
        doc, base_id, target_def = found
        src = self._anchors.get(doc_id, NO_ANCHORS)
        after_build = target_def.uses_anchors(doc.def_id) and not src.known
        new = pack_place(placement, target_def, doc.def_id, self._target.version, src)
        if mark_of(self._state.slots.get(slot_id)) is VisibleMark.plate and not after_build:
            new = widened(self._state, doc_id, slot_id, new)
        pack_moved = self._pack_moved(base_id, doc.def_id, target_def)
        unchanged = placement_digest(new) == placement_digest(placement) and new.enabled == placement.enabled
        if (not pack_moved) if after_build else unchanged:
            return None
        manual = self._places.info(doc_id, slot_id, placement).origin is PlacementOrigin.manual
        if manual and not pack_moved:
            # Пак место этой пары не менял: обновлять нечего, ручное место не новость.
            return None
        reason = kept_reason(doc_id, manual=manual, held_docs=self._held, signed=self._signed)
        return (new, after_build) if reason is None else PresetKept(doc_id, slot_id, reason)

    def _target_of(self, doc_id: str, slot_id: str) -> tuple[Document, str, SignatureSlotDef] | None:
        """Документ, слот каталога и его запись в новой версии; None, если пара в план не входит: экземпляр автора на
        общем документе, слота в новой версии нет, место на якоре на своём загруженном PDF (его ставит человек)."""
        doc = self._docs.get(doc_id)
        base_id, owner = split_instance_id(slot_id)
        if doc is None or (owner is not None and doc.owner is None):
            return None
        target_def = _slot_def(self._target, base_id, doc.def_id)
        if target_def is None:
            return None
        if target_def.uses_anchors(doc.def_id) and self._anchors.get(doc_id, NO_ANCHORS).own_pdf:
            return None
        return doc, base_id, target_def

    def _pack_moved(self, base_id: str, doc_def_id: str, target_def: SignatureSlotDef) -> bool:
        current_def = _slot_def(self._current, base_id, doc_def_id)
        return current_def is None or pack_digest(current_def, doc_def_id) != pack_digest(target_def, doc_def_id)


def plan_signature_presets(  # noqa: PLR0913 — версии и состояние перечислены явно
    templates: ITemplateRepository,
    project: Project,
    current: TemplateVersion,
    target: TemplateVersion,
    state: SignaturesState,
    held_docs: Iterable[str] = (),
    anchors: Mapping[str, SourceAnchors] | None = None,
) -> SignaturePresetsPlan:
    """Что обновление на `target` сделает с местами подписей проекта.

    В план попадают только пары, у которых место после обновления было бы другим: место как в шаблоне и затравка,
    если пресет новой версии с ними расходится (`updated`, или `kept` по маршруту и ЭП), и ручное место, если пак
    поменял место этой пары между версиями (`kept: manual`). Слот общего документа `per_author` пресет не ставит
    (15.5), как и пару, слота которой в новой версии нет или он не применим к документу. `anchors` якоря
    источников подписи по документам (15.17.10); без записи документа якоря неизвестны.
    """
    presets = _Presets(templates, project, current, target, state, held_docs, anchors)
    updated: list[PresetPlace] = []
    placements: list[SignaturePlacement] = []
    kept: list[PresetKept] = []
    for doc_id, slot_map in sorted(state.placements.items()):
        for slot_id, placement in sorted(slot_map.items()):
            outcome = presets.outcome(doc_id, slot_id, placement)
            if isinstance(outcome, PresetKept):
                kept.append(outcome)
            elif outcome is not None:
                updated.append(PresetPlace(doc_id, slot_id, after_build=outcome[1]))
                placements.append(outcome[0])
    return SignaturePresetsPlan(updated=tuple(updated), kept=tuple(kept), placements=tuple(placements))


async def held_docs(routes: ISigningRouteGate, project: Project) -> frozenset[str]:
    """Документы проекта, которые держат маршруты подписания (`HOLDING_STATUSES`): обновление шаблона и его отмена
    их места не трогают. Локально маршрутов нет (`NoSigningRoutes`), и список пуст."""
    return frozenset(doc_id for route in await routes.held_routes(project.id) for doc_id in route.docs)
