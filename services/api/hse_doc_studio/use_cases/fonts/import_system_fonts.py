from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.fonts.entities import InstalledFont
from hse_doc_studio.core.fonts.repositories import IFontStore, ISystemFontProvider
from hse_doc_studio.core.i18n import localized_error


@dataclass
class ImportSystemFontsInput:
    paths: list[str]


@dataclass
class ImportSystemFontsOutput:
    installed: list[InstalledFont]


class ImportSystemFontsUC:
    """Copy already-installed system fonts (by path) into the managed folder."""

    def __init__(self, provider: ISystemFontProvider, store: IFontStore) -> None:
        self._provider = provider
        self._store = store

    async def execute(self, inp: ImportSystemFontsInput) -> ImportSystemFontsOutput:
        if not inp.paths:
            raise ValueError(localized_error("шрифты не выбраны", "no fonts selected"))
        installed: list[InstalledFont] = []
        for path in inp.paths:
            # read_font validates the path is inside a system font directory.
            data = await self._provider.read_font(path)
            installed.append(self._store.save_font(Path(path).name, data))
        return ImportSystemFontsOutput(installed=installed)
