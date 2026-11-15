"""Отслеживание каталогов паков (docs/design/template-studio.md, 10.3, срез T17): раз в сутки по источнику."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI

from hse_doc_studio.core.background import PeriodicTask

if TYPE_CHECKING:
    from dishka import AsyncContainer

    from hse_doc_studio.api.config.settings import Settings

logger = structlog.get_logger()

PACK_CATALOG_TRACK_TASK = "pack_catalog_track"


def install_pack_catalog_tracking(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Источники git с галочкой «Отслеживать», не проверенные больше суток, проверяются; новые выпущенные версии
    применяются, если план чистый. Идёт только у лидера; применённый каталог остальные процессы замечают сами."""
    from hse_doc_studio.use_cases.pack_catalog.service import PackCatalogService  # noqa: PLC0415

    async def _track() -> None:
        applied = await (await container.get(PackCatalogService)).track_due()
        if applied:
            logger.info("pack_catalog_tracked", applied=applied)

    app.state.background.register(
        PeriodicTask(name=PACK_CATALOG_TRACK_TASK, interval_s=cfg.pack_catalog.track_tick_s, run=_track)
    )
