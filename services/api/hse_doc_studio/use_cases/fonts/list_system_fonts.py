from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.fonts.entities import HostFontsUnavailable
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
    # Почему списка нет: «not_shared» — докер не отдал каталог шрифтов (Docker
    # Desktop на macOS), «not_found» — шрифтов там нет. None, когда они есть.
    reason: HostFontsUnavailable | None = None


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
        if fonts:
            return ListSystemFontsOutput(available=True, fonts=fonts)
        reason = await self._provider.unavailable_reason()
        return ListSystemFontsOutput(available=False, fonts=[], reason=reason or "not_found")
