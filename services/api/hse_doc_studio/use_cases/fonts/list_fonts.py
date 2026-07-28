from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.fonts.entities import InstalledFont
from hse_doc_studio.core.fonts.repositories import IFontStore


@dataclass
class ListFontsOutput:
    fonts: list[InstalledFont]


class ListFontsUC:
    def __init__(self, store: IFontStore) -> None:
        self._store = store

    async def execute(self) -> ListFontsOutput:
        return ListFontsOutput(fonts=self._store.list_fonts())
