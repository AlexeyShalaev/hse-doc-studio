"""Места подписей из пака для документов проекта (docs/design/signing-route.md, 15.4 и 15.10).

Сводит чистые правила `core/signatures/pack_places` с версиями шаблона: место из пака берётся из версии проекта,
а затравку узнают по месту из пака этой и всех выпущенных более ранних версий того же шаблона, чтобы patch-версия с
новыми местами не превращала прежние затравки в ручные места.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from hse_doc_studio.core.catalog import SignatureSlotDef, TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import PlacementOrigin, PlaceSource
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.signatures.pack_places import (
    NO_ANCHORS,
    AnchorRef,
    SourceAnchors,
    anchor_ref,
    place_source,
    placement_origin,
    seed_places,
)
from hse_doc_studio.core.team import split_instance_id
from hse_doc_studio.core.template_versions import parse_version_key
from hse_doc_studio.core.value_objects import SignaturePlacement, SignaturesState
from hse_doc_studio.use_cases.signatures.source_anchors import docs_anchors


@dataclass(frozen=True)
class PlaceInfo:
    """Что знает ответ API о месте слота документа (`PlacementResponse.origin`, `preset_available`, 15.11)."""

    origin: PlacementOrigin
    preset_available: bool
    # Какой формой пака задано место, по которому стоит размещение (null у ручного), и якорь места пака у пары с его
    # состоянием в источнике подписи (null у места пака в мм), signing-route.md, 15.17.14.
    source: PlaceSource | None = None
    anchor: AnchorRef | None = None


MANUAL = PlaceInfo(origin=PlacementOrigin.manual, preset_available=False)


def earlier_versions(templates: ITemplateRepository, version: TemplateVersion) -> tuple[TemplateVersion, ...]:
    """Выпущенные версии того же шаблона ниже `version`, от новой к старой; несравнимые номера пропускаются."""
    current = parse_version_key(version.version)
    if current is None:
        return ()
    keyed = [
        (key, version_id)
        for version_id in templates.list_versions(version.pack_id, version.template_id)
        if (key := parse_version_key(version_id)) is not None and key < current
    ]
    found = (templates.get_version(version.pack_id, version.template_id, v) for _, v in sorted(keyed, reverse=True))
    return tuple(v for v in found if v is not None)


class PackPlaces:
    """Место из пака, затравка и происхождение размещений одного проекта на его версии шаблона."""

    def __init__(
        self,
        project: Project,
        version: TemplateVersion,
        earlier: Sequence[TemplateVersion] = (),
        anchors: Mapping[str, SourceAnchors] | None = None,
    ) -> None:
        self._docs = {doc.id: doc.def_id for doc in project.documents}
        self._versions = (version, *earlier)
        self._anchors = dict(anchors or {})

    @classmethod
    def load(
        cls,
        templates: ITemplateRepository,
        project: Project,
        version: TemplateVersion,
        anchors: Mapping[str, SourceAnchors] | None = None,
    ) -> PackPlaces:
        """`anchors` якоря источников подписи по документам (15.17.8): по ним состояние якоря места; без записи
        документа якоря считаются неизвестными."""
        return cls(project, version, earlier_versions(templates, version), anchors)

    def _slot_defs(self, slot_id: str) -> list[SignatureSlotDef]:
        """Слот каталога рантайм-слота (`author--<слаг>` это `author`) в версии проекта и в более ранних."""
        base_id = split_instance_id(slot_id)[0]
        found = (next((s for s in v.signatures_config.slots if s.id == base_id), None) for v in self._versions)
        return [slot_def for slot_def in found if slot_def is not None]

    def _current(self, doc_id: str, slot_id: str) -> tuple[SignatureSlotDef, str] | None:
        """Слот каталога версии проекта и id определения документа, если слот применим к документу."""
        def_id = self._docs.get(doc_id)
        base_id = split_instance_id(slot_id)[0]
        slot_def = next((s for s in self._versions[0].signatures_config.slots if s.id == base_id), None)
        if def_id is None or slot_def is None or def_id not in slot_def.applies_to:
            return None
        return slot_def, def_id

    def available(self, doc_id: str, slot_id: str) -> bool:
        """В шаблоне проекта есть место этого слота для документа: слот есть и применим к документу."""
        return self._current(doc_id, slot_id) is not None

    def anchor(self, doc_id: str, slot_id: str) -> AnchorRef | None:
        """Якорь места пака у пары и его состояние в источнике подписи; None у места пака в мм и без места."""
        current = self._current(doc_id, slot_id)
        if current is None:
            return None
        return anchor_ref(current[0], current[1], self._anchors.get(doc_id, NO_ANCHORS))

    def info(self, doc_id: str, slot_id: str, placement: SignaturePlacement) -> PlaceInfo:
        def_id = self._docs.get(doc_id)
        seeds = seed_places(self._slot_defs(slot_id), def_id) if def_id is not None else ()
        origin = placement_origin(placement, seeds)
        return PlaceInfo(
            origin=origin,
            preset_available=self.available(doc_id, slot_id),
            source=place_source(placement, origin),
            anchor=self.anchor(doc_id, slot_id),
        )

    def infos(self, placements: dict[str, dict[str, SignaturePlacement]]) -> dict[str, dict[str, PlaceInfo]]:
        return {
            doc_id: {slot_id: self.info(doc_id, slot_id, placement) for slot_id, placement in slot_map.items()}
            for doc_id, slot_map in placements.items()
        }


async def load_places(  # noqa: PLR0913 — версии, состояние и документы перечислены явно
    templates: ITemplateRepository,
    template_service: ProjectTemplateService | None,
    project: Project,
    version: TemplateVersion,
    state: SignaturesState,
    doc_ids: Iterable[str] | None = None,
) -> PackPlaces:
    """`PackPlaces` с якорями источников подписи документов `doc_ids` (без них всех): по ним `source` и `anchor`
    мест (15.17.14). Без сервиса шаблонов якоря неизвестны."""
    anchors = (
        await docs_anchors(template_service, project, version, state, doc_ids) if template_service is not None else {}
    )
    return PackPlaces.load(templates, project, version, anchors)
