"""Действующие настройки личных раннеров: ключи `runners.*` в instance_settings и окружение поверх них.

Значение читает каждая постановка задачи и каждый опрос личного раннера, поэтому оно держится в памяти
несколько секунд; правка админа сбрасывает запомненное сразу (`invalidate`).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from hse_doc_studio.core.identity.instance_settings import InstanceEnvOverrides, effective_personal_runner_settings
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.jobs.routing import PersonalRunnerSettings

CACHE_TTL_S = 2.0


class InstancePersonalRunnerSettings:
    def __init__(
        self,
        repo: IInstanceSettingsRepository,
        env: InstanceEnvOverrides,
        *,
        ttl_s: float = CACHE_TTL_S,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repo = repo
        self._env = env
        self._ttl_s = ttl_s
        self._monotonic = monotonic
        self._cached: tuple[float, PersonalRunnerSettings] | None = None

    async def current(self) -> PersonalRunnerSettings:
        now = self._monotonic()
        if self._cached is not None and now - self._cached[0] < self._ttl_s:
            return self._cached[1]
        value = effective_personal_runner_settings(await self._repo.get_all(), self._env)
        self._cached = (now, value)
        return value

    def invalidate(self) -> None:
        self._cached = None
