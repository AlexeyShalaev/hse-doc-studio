from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.fonts.repositories import IFontStore
from hse_doc_studio.core.i18n import localized_error


@dataclass
class RemoveFontInput:
    name: str


class RemoveFontUC:
    def __init__(self, store: IFontStore) -> None:
        self._store = store

    async def execute(self, inp: RemoveFontInput) -> None:
        if not self._store.delete_font(inp.name):
            raise NotFoundError(localized_error(f"шрифт не найден: {inp.name!r}", f"font not found: {inp.name!r}"))
