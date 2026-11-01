"""Пороги занятости диска и безопасный режим: что делать, когда место кончается."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum

KEY_WARN_PERCENT = "storage.warn_percent"
KEY_CRITICAL_PERCENT = "storage.critical_percent"

DEFAULT_WARN_PERCENT = 80
DEFAULT_CRITICAL_PERCENT = 90
WARN_RANGE = (50, 95)
CRITICAL_RANGE = (60, 99)

# В безопасном режиме крупными считаются записи тела больше этого предела: мелкие правки продолжают работать,
# чтобы человек мог сохранить набранное и освободить место.
SAFE_MODE_MAX_BODY_BYTES = 1024 * 1024


class StorageLevel(IntEnum):
    ok = 0
    warning = 1
    critical = 2


@dataclass(frozen=True)
class StorageThresholds:
    warn_percent: int = DEFAULT_WARN_PERCENT
    critical_percent: int = DEFAULT_CRITICAL_PERCENT

    def level(self, used_ratio: float | None) -> StorageLevel:
        if used_ratio is None:
            return StorageLevel.ok
        percent = used_ratio * 100
        if percent >= self.critical_percent:
            return StorageLevel.critical
        if percent >= self.warn_percent:
            return StorageLevel.warning
        return StorageLevel.ok


def effective_thresholds(stored: Mapping[str, object]) -> StorageThresholds:
    """Правка админа в границах; пара должна сохранять порядок (предупреждение раньше критического)."""

    def pick(key: str, bounds: tuple[int, int], default: int) -> int:
        raw = stored.get(key)
        return raw if isinstance(raw, int) and not isinstance(raw, bool) and bounds[0] <= raw <= bounds[1] else default

    warn = pick(KEY_WARN_PERCENT, WARN_RANGE, DEFAULT_WARN_PERCENT)
    critical = pick(KEY_CRITICAL_PERCENT, CRITICAL_RANGE, DEFAULT_CRITICAL_PERCENT)
    if critical <= warn:
        return StorageThresholds()
    return StorageThresholds(warn, critical)


class SafeMode:
    """Флаг безопасного режима процесса: его выставляет проба места, читает middleware загрузок и метрики."""

    def __init__(self) -> None:
        self._active = False
        self._reason: str | None = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def reason(self) -> str | None:
        return self._reason

    def set(self, active: bool, reason: str | None = None) -> None:
        self._active = active
        self._reason = reason if active else None


# Один флаг на процесс: его выставляет проба места, читают middleware загрузок, метрики и админка.
PROCESS_SAFE_MODE = SafeMode()
