from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.fonts.entities import InstalledFont
from hse_doc_studio.core.fonts.repositories import IFontStore
from hse_doc_studio.core.i18n import localized_error


@dataclass
class UploadFontInput:
    filename: str
    content: bytes


@dataclass
class UploadFontOutput:
    font: InstalledFont


class UploadFontUC:
    def __init__(self, store: IFontStore) -> None:
        self._store = store

    async def execute(self, inp: UploadFontInput) -> UploadFontOutput:
        if not inp.content:
            raise ValueError(localized_error("пустой файл шрифта", "empty font file"))
        # store.save_font validates the extension and strips any path components.
        return UploadFontOutput(font=self._store.save_font(inp.filename, inp.content))
