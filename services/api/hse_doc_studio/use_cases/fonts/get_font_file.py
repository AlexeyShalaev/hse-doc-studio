from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.fonts.repositories import IFontStore
from hse_doc_studio.core.i18n import localized_error


@dataclass
class GetFontFileInput:
    filename: str


@dataclass
class GetFontFileOutput:
    filename: str
    content: bytes


class GetFontFileUC:
    """Serve the raw bytes of a managed font (for in-app previews)."""

    def __init__(self, store: IFontStore) -> None:
        self._store = store

    async def execute(self, inp: GetFontFileInput) -> GetFontFileOutput:
        data = self._store.read_font(inp.filename)
        if data is None:
            raise NotFoundError(
                localized_error(f"шрифт не найден: {inp.filename!r}", f"font not found: {inp.filename!r}")
            )
        return GetFontFileOutput(filename=Path(inp.filename).name, content=data)
