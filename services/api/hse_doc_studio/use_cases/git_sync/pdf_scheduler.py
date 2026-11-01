"""Фоновая выгрузка PDF после сборки: по одной задаче на документ, повторные сборки не копятся в очередь."""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog

from hse_doc_studio.use_cases.git_sync.publish_pdf import PublishPdfUC

logger = structlog.get_logger()


class PdfPublishScheduler:
    """`IBuiltPdfObserver` локальной Студии. Пока документ выгружается, новая сборка лишь помечает его «ещё раз»."""

    def __init__(self, publish: PublishPdfUC) -> None:
        self._publish = publish
        self._tasks: dict[tuple[UUID, str], asyncio.Task[None]] = {}
        self._again: dict[tuple[UUID, str], int | None] = {}

    def on_pdf_built(self, project_id: UUID, doc_id: str, pages: int | None) -> None:
        key = (project_id, doc_id)
        if key in self._tasks:
            self._again[key] = pages
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._tasks[key] = loop.create_task(self._run(key, pages), name=f"pdf-publish-{doc_id}")

    async def _run(self, key: tuple[UUID, str], pages: int | None) -> None:
        project_id, doc_id = key
        try:
            while True:
                try:
                    await self._publish.execute(project_id, doc_id, pages=pages)
                except Exception:  # noqa: BLE001 — выгрузка не должна ронять фоновую задачу сборки
                    logger.warning("pdf publish failed", project_id=str(project_id), doc_id=doc_id, exc_info=True)
                if key not in self._again:
                    return
                pages = self._again.pop(key)
        finally:
            self._tasks.pop(key, None)
            self._again.pop(key, None)

    async def drain(self) -> None:
        """Дождаться идущих выгрузок (тесты и остановка приложения)."""
        while self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
