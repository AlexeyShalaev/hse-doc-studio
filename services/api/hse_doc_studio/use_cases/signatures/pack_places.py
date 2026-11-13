"""Места подписей из пака для документов проекта (docs/design/signing-route.md, 15.4 и 15.10).

Сводит чистые правила `core/signatures/pack_places` с версиями шаблона: место из пака берётся из версии проекта,
а затравку узнают по месту из пака этой и всех выпущенных более ранних версий того же шаблона, чтобы patch-версия с
новыми местами не превращала прежние затравки в ручные места.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from hse_doc_studio.core.catalog import SignatureSlotDef, TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import PlacementOrigin
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.signatures.pack_places import placement_origin, seed_places
from hse_doc_studio.core.team import split_instance_id
from hse_doc_studio.core.template_versions import parse_version_key
from hse_doc_studio.core.value_objects import SignaturePlacement


@dataclass(frozen=True)
class PlaceInfo:
    """Что знает ответ API о месте слота документа (`PlacementResponse.origin`, `preset_available`, 15.11)."""

    origin: PlacementOrigin
    preset_available: bool


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

    def __init__(self, project: Project, version: TemplateVersion, earlier: Sequence[TemplateVersion] = ()) -> None:
        self._docs = {doc.id: doc.def_id for doc in project.documents}
        self._versions = (version, *earlier)

    @classmethod
    def load(cls, templates: ITemplateRepository, project: Project, version: TemplateVersion) -> PackPlaces:
        return cls(project, version, earlier_versions(templates, version))

    def _slot_defs(self, slot_id: str) -> list[SignatureSlotDef]:
        """Слот каталога рантайм-слота (`author--<слаг>` это `author`) в версии проекта и в более ранних."""
        base_id = split_instance_id(slot_id)[0]
        found = (next((s for s in v.signatures_config.slots if s.id == base_id), None) for v in self._versions)
        return [slot_def for slot_def in found if slot_def is not None]

    def available(self, doc_id: str, slot_id: str) -> bool:
        """В шаблоне проекта есть место этого слота для документа: слот есть и применим к документу."""
        def_id = self._docs.get(doc_id)
        base_id = split_instance_id(slot_id)[0]
        slot_def = next((s for s in self._versions[0].signatures_config.slots if s.id == base_id), None)
        return def_id is not None and slot_def is not None and def_id in slot_def.applies_to

    def info(self, doc_id: str, slot_id: str, placement: SignaturePlacement) -> PlaceInfo:
        def_id = self._docs.get(doc_id)
        seeds = seed_places(self._slot_defs(slot_id), def_id) if def_id is not None else ()
        return PlaceInfo(origin=placement_origin(placement, seeds), preset_available=self.available(doc_id, slot_id))

    def infos(self, placements: dict[str, dict[str, SignaturePlacement]]) -> dict[str, dict[str, PlaceInfo]]:
        return {
            doc_id: {slot_id: self.info(doc_id, slot_id, placement) for slot_id, placement in slot_map.items()}
            for doc_id, slot_map in placements.items()
        }
