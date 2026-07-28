from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hse_doc_studio.core.fonts.entities import (
    FontCatalogFile,
    InstalledFont,
    MarketplaceSearchResult,
    SystemFontFile,
)


class IFontStore(Protocol):
    """Manages the TTF/OTF files in the user's local fonts folder (<data_dir>/fonts)."""

    @property
    def fonts_dir(self) -> Path: ...

    def list_fonts(self) -> list[InstalledFont]: ...

    def save_font(self, filename: str, content: bytes) -> InstalledFont: ...

    def delete_font(self, filename: str) -> bool: ...

    # Raw bytes of a managed font (basename-sanitized), or None if absent. Used to
    # serve installed fonts back to the UI for in-app previews.
    def read_font(self, filename: str) -> bytes | None: ...

    def has_fonts(self) -> bool: ...


class IFontDownloader(Protocol):
    """Fetches a font file from an HTTPS URL (curated catalog downloads)."""

    async def download(self, url: str) -> bytes: ...


class ISystemFontProvider(Protocol):
    """Шрифты, установленные на машине ПОЛЬЗОВАТЕЛЯ.

    Нативно это стандартные каталоги ОС, в контейнере — они же, но увиденные
    через docker-сокет одноразовым контейнером. Асинхронный протокол именно
    поэтому: контейнерная реализация ходит в докер, а нативная обходит дерево
    каталогов, открывая каждый файл ради имени семейства, — и то и другое
    нельзя делать прямо в event loop.
    """

    async def list_fonts(self) -> list[SystemFontFile]: ...

    # Каталог, из которого шрифты и читаются; None — ни один не подошёл.
    # Показывается пользователю: автоопределение может промахнуться, и тогда
    # он должен видеть, ЧТО именно приложение сочло каталогом шрифтов.
    async def source_dir(self) -> str | None: ...

    # Reads a system font's bytes. MUST reject any path that is not inside a
    # known system font directory (and not a font file) to keep the import
    # endpoint from being used to read arbitrary files.
    async def read_font(self, path: str) -> bytes: ...


class IFontMarketplace(Protocol):
    """Searchable online font library (Google Fonts), limited to families that
    ship static TTFs. Best-effort: falls back to a small bundled set offline."""

    async def search(
        self, query: str, category: str | None, cyrillic_only: bool, limit: int, offset: int
    ) -> MarketplaceSearchResult: ...

    # Download specs (filename + url) for a marketplace font id, or [] if unknown.
    async def get_files(self, font_id: str) -> list[FontCatalogFile]: ...
