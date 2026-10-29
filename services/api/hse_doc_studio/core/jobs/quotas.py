"""Квоты задач установки: одновременные задачи и предельная длительность.

Значения лежат в `instance_settings`; `None` значит без лимита. При исчерпании задача ждёт в очереди
(поведение сверх квоты появится на этапе 6), поэтому здесь только числа и их проверка.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from hse_doc_studio.core.jobs.scheduler import QueueQuota

KEY_USER_CONCURRENT = "jobs.concurrent"
KEY_ORG_CONCURRENT = "jobs.org_concurrent"
KEY_MAX_DURATION_S = "jobs.max_duration_s"
QUOTA_KEYS = (KEY_USER_CONCURRENT, KEY_ORG_CONCURRENT, KEY_MAX_DURATION_S)

MAX_CONCURRENT = 1000
MIN_DURATION_S = 10
MAX_DURATION_S = 24 * 3600


class QuotaValueError(ValueError):
    """Значение квоты вне допустимого; `field` называет поле запроса."""

    def __init__(self, field: str) -> None:
        super().__init__(f"quota value out of range: {field}")
        self.field = field


@dataclass(frozen=True)
class QuotaSettings:
    user_concurrent: int | None = None
    org_concurrent: int | None = None
    max_duration_s: int | None = None

    def __post_init__(self) -> None:
        for name in ("user_concurrent", "org_concurrent"):
            value = getattr(self, name)
            if value is not None and not 1 <= value <= MAX_CONCURRENT:
                raise QuotaValueError(name)
        if self.max_duration_s is not None and not MIN_DURATION_S <= self.max_duration_s <= MAX_DURATION_S:
            raise QuotaValueError("max_duration_s")

    def to_queue_quota(self) -> QueueQuota:
        return QueueQuota(
            max_running_per_user=self.user_concurrent,
            max_running_per_org=self.org_concurrent,
            max_timeout_s=float(self.max_duration_s) if self.max_duration_s is not None else None,
        )


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def quota_settings_from(values: Mapping[str, object]) -> QuotaSettings:
    """Испорченное значение в базе не должно останавливать очередь: оно читается как «без лимита»."""
    try:
        return QuotaSettings(
            user_concurrent=_int_or_none(values.get(KEY_USER_CONCURRENT)),
            org_concurrent=_int_or_none(values.get(KEY_ORG_CONCURRENT)),
            max_duration_s=_int_or_none(values.get(KEY_MAX_DURATION_S)),
        )
    except QuotaValueError:
        return QuotaSettings()
