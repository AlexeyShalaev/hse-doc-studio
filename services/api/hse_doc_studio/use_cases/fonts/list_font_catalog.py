from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.fonts.entities import FontCatalog
from hse_doc_studio.core.fonts.repositories import IFontStore


@dataclass
class CatalogItemView:
    id: str
    label: str
    family: str
    description: str
    license: str
    file_count: int
    installed: bool  # True when every file of the entry is already present


@dataclass
class ListFontCatalogOutput:
    items: list[CatalogItemView]


class ListFontCatalogUC:
    def __init__(self, catalog: FontCatalog, store: IFontStore) -> None:
        self._catalog = catalog
        self._store = store

    async def execute(self) -> ListFontCatalogOutput:
        present = {f.name for f in self._store.list_fonts()}
        items = [
            CatalogItemView(
                id=item.id,
                label=item.label,
                family=item.family,
                description=item.description,
                license=item.license,
                file_count=len(item.files),
                installed=bool(item.files) and all(f.filename in present for f in item.files),
            )
            for item in self._catalog.items
        ]
        return ListFontCatalogOutput(items=items)
