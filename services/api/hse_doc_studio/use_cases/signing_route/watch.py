"""Наблюдатель за изменениями проекта мимо маршрута (docs/design/signing-route.md, раздел 5.5).

Хуки (сборка, запись состояния подписей, синхронизация, восстановление из истории, уход участника) зовут
`RouteWatch.on_project_changed`. Он ничего не блокирует и не считает сам, а ставит сверку маршрутов проекта в
очередь: по одной задаче на проект, повторные изменения во время сверки дают ещё один проход, а не копятся.

Отложенная сверка снимает вопрос повторного входа. Хук записи подписей срабатывает и внутри сценариев маршрута
(они сами пишут `signatures.json`) и под `project_lock`; сверка в этот момент взяла бы строку маршрута в обратном
порядке блокировок или остановила маршрут по его же правке. Задача сверки берёт строку маршрута сама и поэтому ждёт
конца транзакции сценария, а затем видит снимок, который тот уже обновил.

Задача идёт в пустом контексте: без актора и без транзакции запроса, из которого её поставили.
"""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Awaitable, Callable
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import ISignatureRepository
from hse_doc_studio.core.signing_route.ports import IRouteWatch
from hse_doc_studio.core.value_objects import SignaturesState

logger = structlog.get_logger()

Reconcile = Callable[[UUID], Awaitable[object]]
ProjectIdOf = Callable[[Path], UUID]


class RouteWatch:
    """`IRouteWatch` и `IBuiltPdfObserver` сервера."""

    def __init__(self, reconcile: Reconcile) -> None:
        self._reconcile = reconcile
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._again: set[UUID] = set()
        self._loop = _running_loop()

    def on_project_changed(self, project_id: UUID) -> None:
        loop = _running_loop()
        if loop is not None:
            self._loop = loop
            self._schedule(project_id)
            return
        # Вызов из рабочего потока (`asyncio.to_thread`): задачу ставит цикл приложения.
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._schedule, project_id)

    def on_pdf_built(self, project_id: UUID, doc_id: str, pages: int | None) -> None:
        """Сборка документа удалась: другой PDF останавливает маршрут, тот же (сборка воспроизводима) нет."""
        self.on_project_changed(project_id)

    def _schedule(self, project_id: UUID) -> None:
        if project_id in self._tasks:
            self._again.add(project_id)
            return
        loop = asyncio.get_running_loop()
        self._tasks[project_id] = loop.create_task(
            self._run(project_id), name=f"signing-route-watch-{project_id}", context=contextvars.Context()
        )

    async def _run(self, project_id: UUID) -> None:
        try:
            while True:
                self._again.discard(project_id)
                try:
                    await self._reconcile(project_id)
                except Exception:  # noqa: BLE001 — сверка не должна ронять фоновую задачу; её повторит периодическая
                    logger.warning("signing routes not reconciled", project_id=str(project_id), exc_info=True)
                if project_id not in self._again:
                    return
        finally:
            self._tasks.pop(project_id, None)
            self._again.discard(project_id)

    async def drain(self) -> None:
        """Дождаться идущих сверок (тесты и остановка приложения)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


class WatchedSignatureRepository:
    """`ISignatureRepository`, который после каждой записи состояния подписей зовёт наблюдателя маршрутов.

    Запись идёт и из сценариев маршрута, и под `project_lock`: наблюдатель только ставит сверку в очередь.
    `project_id_of` id проекта по его папке (на сервере это том проектов, `IProjectVolume.id_of`).
    """

    def __init__(self, inner: ISignatureRepository, project_id_of: ProjectIdOf, watch: IRouteWatch) -> None:
        self._inner = inner
        self._project_id_of = project_id_of
        self._watch = watch

    def get_state(self, project_folder: Path) -> SignaturesState:
        return self._inner.get_state(project_folder)

    def save_state(self, project_folder: Path, state: SignaturesState) -> None:
        self._inner.save_state(project_folder, state)
        try:
            self._watch.on_project_changed(self._project_id_of(project_folder))
        except Exception:  # noqa: BLE001 — состояние уже записано; папка вне тома или сбой: догонит периодическая сверка
            logger.debug("signing route watch not notified", folder=str(project_folder), exc_info=True)
