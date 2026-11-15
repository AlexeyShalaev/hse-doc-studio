"""Задачи `compile` сборок предпросмотра (порт IPreviewDispatcher, docs/design/template-studio.md, D14).

Отдельного вида задачи нет: тот же latexmk, тот же исполнитель, та же очередь. Отличается только место папки
синтетического проекта.

- Локально это общий встроенный диспетчер: задача несёт папку сборки в `local_root`, исполнитель собирает в ней.
- На сервере вход задачи грузится в хранилище из папки на томе предпросмотра (`previews/work/<id задачи>`), а не
  с тома проектов, и выходы раннера кладутся туда же. Поэтому серверный диспетчер предпросмотра это отдельный
  экземпляр `QueueJobDispatcher` с теми же очередью, раннерами, квотами и маршрутами, но со своими загрузчиком
  (без кэша хешей: его строки ссылаются на проекты) и применением выходов (PDF не уходит в архив проекта).
  Восстановление после рестарта у него выключено: сборку предпросмотра проще собрать заново.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Mapping
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.jobs.entities import JobSpec
from hse_doc_studio.core.jobs.protocols import IJobDispatcher, IJobHooks
from hse_doc_studio.core.storage.manifest import HashCacheEntry, IBlobRegistry, UnreferencedBlob


class PreviewJobDispatcher:
    def __init__(self, inner: IJobDispatcher) -> None:
        self._inner = inner

    async def preflight(self, spec: JobSpec) -> None:
        await self._inner.preflight(spec)

    def submit(self, spec: JobSpec, hooks: IJobHooks) -> None:
        self._inner.submit(spec, hooks)

    async def cancel(self, job_id: UUID) -> bool:
        return await self._inner.cancel(job_id)

    def is_active(self, job_id: UUID) -> bool:
        return self._inner.is_active(job_id)


class NoHashCacheRegistry:
    """Реестр блобов без кэша хешей файлов: у папки сборки предпросмотра нет строки проекта, на которую он ссылается,
    а сама папка живёт одну сборку. Остальное (наличие блобов, защита от уборки) как у общего реестра."""

    def __init__(self, inner: IBlobRegistry) -> None:
        self._inner = inner

    async def touch(self, shas: Collection[str], now: datetime) -> set[str]:
        return await self._inner.touch(shas, now)

    async def record(self, blobs: Mapping[str, int], now: datetime) -> None:
        await self._inner.record(blobs, now)

    async def known(self, shas: Collection[str]) -> set[str]:
        return await self._inner.known(shas)

    async def forget(self, shas: Collection[str]) -> None:
        await self._inner.forget(shas)

    async def hash_cache(self, project_id: UUID, paths: Collection[str]) -> dict[str, HashCacheEntry]:
        return {}

    async def store_hash_cache(self, project_id: UUID, entries: Mapping[str, HashCacheEntry]) -> None:
        return

    async def reap(
        self,
        older_than: datetime,
        limit: int,
        remove: Callable[[str], Awaitable[None]],
        *,
        keep: Collection[str] = (),
    ) -> list[UnreferencedBlob]:
        return await self._inner.reap(older_than, limit, remove, keep=keep)
