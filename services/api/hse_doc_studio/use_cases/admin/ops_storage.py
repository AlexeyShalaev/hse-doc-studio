"""Занятое место для админки: счёт по базе, результат хранится минуту, чтобы экран не нагружал её."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import replace

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.listing import Found, Window, clamp_limit
from hse_doc_studio.core.storage.usage import IStorageUsageReader, StorageOwner, StorageOwnerQuery, StorageUsage
from hse_doc_studio.use_cases.admin.users import require_admin

USAGE_TTL_S = 60.0


class GetStorageUsageUC:
    def __init__(
        self,
        reader: IStorageUsageReader,
        *,
        ttl_s: float = USAGE_TTL_S,
        clock: Clock = utc_now,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._reader = reader
        self._ttl = ttl_s
        self._clock = clock
        self._monotonic = monotonic or time.monotonic
        self._cached: tuple[float, StorageUsage] | None = None
        self._lock = asyncio.Lock()

    async def execute(self, actor: Actor, *, refresh: bool = False) -> StorageUsage:
        require_admin(actor)
        async with self._lock:
            now = self._monotonic()
            if refresh or self._cached is None or now - self._cached[0] >= self._ttl:
                self._cached = (now, await self._reader.read(self._clock()))
            return self._cached[1]


class ListStorageOwnersUC:
    """Владельцы по занятому месту: страница прямо из базы, без кэша сводки."""

    def __init__(self, reader: IStorageUsageReader) -> None:
        self._reader = reader

    async def execute(self, actor: Actor, query: StorageOwnerQuery) -> Found[StorageOwner]:
        require_admin(actor)
        window = Window(limit=clamp_limit(query.window.limit), offset=max(0, query.window.offset))
        return await self._reader.list_owners(replace(query, window=window))
