from __future__ import annotations

from dataclasses import dataclass

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.fonts.entities import InstalledFont
from hse_doc_studio.core.fonts.repositories import IFontDownloader, IFontMarketplace, IFontStore
from hse_doc_studio.core.i18n import localized_error

logger = structlog.get_logger()


@dataclass
class InstallMarketplaceFontInput:
    id: str


@dataclass
class InstallMarketplaceFontOutput:
    installed: list[InstalledFont]


class InstallMarketplaceFontUC:
    """Download a marketplace font's static TTFs into the managed folder."""

    def __init__(self, marketplace: IFontMarketplace, downloader: IFontDownloader, store: IFontStore) -> None:
        self._marketplace = marketplace
        self._downloader = downloader
        self._store = store

    async def execute(self, inp: InstallMarketplaceFontInput) -> InstallMarketplaceFontOutput:
        files = await self._marketplace.get_files(inp.id)
        if not files:
            raise NotFoundError(
                localized_error(f"неизвестный шрифт маркетплейса: {inp.id!r}", f"unknown marketplace font: {inp.id!r}")
            )
        installed: list[InstalledFont] = []
        for file in files:
            try:
                data = await self._downloader.download(file.url)
            except Exception as exc:  # noqa: BLE001 — surface a clean message to the API
                raise ValueError(
                    localized_error(
                        f"не удалось скачать {file.filename}: {exc}", f"failed to download {file.filename}: {exc}"
                    )
                ) from exc
            installed.append(self._store.save_font(file.filename, data))
        logger.info("marketplace font installed", id=inp.id, files=len(installed))
        return InstallMarketplaceFontOutput(installed=installed)
