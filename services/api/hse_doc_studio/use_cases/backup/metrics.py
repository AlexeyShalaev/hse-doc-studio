"""Снимок состояния бэкапов для метрик Prometheus.

Сборщик метрик синхронный, а данные в базе, поэтому снимок обновляется асинхронно: на старте, на каждом тике
планировщика и после запуска (см. `install_backups`). Счётчики берутся из таблицы запусков, а не из памяти процесса:
они переживают перезапуск api.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hse_doc_studio.core.backup.entities import BackupRun, RunStats, RunStatus
from hse_doc_studio.core.backup.protocols import IBackupRunRepository
from hse_doc_studio.core.backup.settings import settings_from
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository


@dataclass
class BackupMetricsState:
    enabled: bool = False
    running: bool = False
    stats: RunStats = field(default_factory=RunStats)
    loaded: bool = False

    @property
    def last_success(self) -> BackupRun | None:
        return self.stats.last_success

    def count(self, status: RunStatus) -> int:
        return self.stats.by_status.get(status, 0)


class BackupMetricsRefresher:
    def __init__(
        self, state: BackupMetricsState, runs: IBackupRunRepository, settings_repo: IInstanceSettingsRepository
    ) -> None:
        self._state = state
        self._runs = runs
        self._settings = settings_repo

    async def refresh(self) -> None:
        stats = await self._runs.stats()
        running = await self._runs.running()
        settings = settings_from(await self._settings.get_all())
        self._state.stats = stats
        self._state.running = running is not None
        self._state.enabled = settings.enabled
        self._state.loaded = True
