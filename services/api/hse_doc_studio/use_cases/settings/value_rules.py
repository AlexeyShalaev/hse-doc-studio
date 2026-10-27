"""Правила значений числовых настроек: одни и те же для PUT /settings и для загрузки файла переноса."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hse_doc_studio.core.git_sync.policy import MIN_FETCH_INTERVAL_S

MAX_DISK_USAGE_WARN_GB = 500


def git_fetch_interval_s(value: object) -> int | None:
    """0 выключает проверку, всё, что меньше минуты, поднимается до минуты; None: значение не годится."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return 0 if value == 0 else max(MIN_FETCH_INTERVAL_S, value)


def disk_usage_warn_gb(value: object) -> int | None:
    """Порог в гигабайтах от 0 (предупреждение выключено) до 500; None: значение не годится."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_DISK_USAGE_WARN_GB:
        return None
    return value


# Настройки с правилами. Остальные принимают любое значение, как и раньше.
SETTING_VALUE_RULES: dict[str, Callable[[object], Any]] = {
    "git_fetch_interval_s": git_fetch_interval_s,
    "disk_usage_warn_gb": disk_usage_warn_gb,
}
