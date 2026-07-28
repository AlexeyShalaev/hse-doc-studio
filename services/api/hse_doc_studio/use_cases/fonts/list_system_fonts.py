from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.fonts.repositories import IFontStore, ISystemFontProvider


@dataclass
class SystemFontView:
    name: str
    path: str
    family: str
    already_installed: bool


@dataclass
class ListSystemFontsOutput:
    # available=False when the host exposes no font directories (e.g. the backend
    # runs in a container without the host fonts mounted) — the UI hides the picker.
    available: bool
    fonts: list[SystemFontView]


class ListSystemFontsUC:
    def __init__(self, provider: ISystemFontProvider, store: IFontStore) -> None:
        self._provider = provider
        self._store = store

    async def execute(self) -> ListSystemFontsOutput:
        present = {f.name for f in self._store.list_fonts()}
        system = await self._provider.list_fonts()
        fonts = [
            SystemFontView(name=f.name, path=f.path, family=f.family, already_installed=f.name in present)
            for f in system
        ]
        return ListSystemFontsOutput(available=len(fonts) > 0, fonts=fonts)
