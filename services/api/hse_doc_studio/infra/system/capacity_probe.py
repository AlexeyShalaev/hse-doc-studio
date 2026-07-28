from __future__ import annotations

import os
import shutil
from contextlib import suppress
from pathlib import Path

import psutil
import structlog

from hse_doc_studio.core.system_capacity import SystemCapacity

logger = structlog.get_logger()

_MB_PER_BYTE = 1024 * 1024


class SystemCapacityProbe:
    """Ресурсы машины для дефолтов настроек (ядра / память / объём диска).

    Каждый замер обёрнут так, что определение НИКОГДА не падает: неизвестное поле
    возвращается как ``None``, и домен подставляет консервативный дефолт. Диск
    меряется по каталогу данных: в контейнере это тот же том, где докер держит
    образы, а нативно — диск пользователя.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def detect(self) -> SystemCapacity:
        return SystemCapacity(
            cpu_count=self._cpu_count(),
            total_ram_mb=self._total_ram_mb(),
            disk_total_bytes=self._disk_total_bytes(),
        )

    @staticmethod
    def _cpu_count() -> int | None:
        with suppress(Exception):
            return os.cpu_count()
        return None

    @staticmethod
    def _total_ram_mb() -> int | None:
        with suppress(Exception):
            return int(psutil.virtual_memory().total // _MB_PER_BYTE)
        return None

    def _disk_total_bytes(self) -> int | None:
        # Каталога данных может ещё не быть на самом первом запуске — тогда меряем
        # ближайший существующий родительский каталог, он на том же томе.
        probe = self._data_dir
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        with suppress(Exception):
            return int(shutil.disk_usage(probe).total)
        return None
