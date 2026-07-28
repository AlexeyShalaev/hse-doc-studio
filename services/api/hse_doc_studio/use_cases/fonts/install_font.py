from __future__ import annotations

from dataclasses import dataclass

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.fonts.entities import FontCatalog, InstalledFont
from hse_doc_studio.core.fonts.repositories import IFontDownloader, IFontStore
from hse_doc_studio.core.i18n import localized_error

logger = structlog.get_logger()


@dataclass
class InstallFontInput:
    id: str


@dataclass
class InstallFontOutput:
    installed: list[InstalledFont]


class InstallFontUC:
    """Download every file of a curated catalog font into the managed folder."""

    def __init__(self, catalog: FontCatalog, downloader: IFontDownloader, store: IFontStore) -> None:
        self._catalog = catalog
        self._downloader = downloader
        self._store = store

    async def execute(self, inp: InstallFontInput) -> InstallFontOutput:
        item = self._catalog.get(inp.id)
        if item is None:
            raise NotFoundError(
                localized_error(f"неизвестный шрифт каталога: {inp.id!r}", f"unknown catalog font: {inp.id!r}")
            )
        installed: list[InstalledFont] = []
        for file in item.files:
            try:
                data = await self._downloader.download(file.url)
            except Exception as exc:  # noqa: BLE001 — surface a clean message to the API
                raise ValueError(
                    localized_error(
                        f"не удалось скачать {file.filename}: {exc}", f"failed to download {file.filename}: {exc}"
                    )
                ) from exc
            installed.append(self._store.save_font(file.filename, data))
        logger.info("catalog font installed", id=item.id, files=len(installed))
        return InstallFontOutput(installed=installed)
