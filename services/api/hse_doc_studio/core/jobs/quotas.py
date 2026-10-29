"""Квоты задач установки: одновременные задачи и предельная длительность.

Значения лежат в `instance_settings`; `None` значит без лимита. При исчерпании задача ждёт в очереди
(поведение сверх квоты появится на этапе 6), поэтому здесь только числа и их проверка.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol
from uuid import NAMESPACE_OID, UUID, uuid5

from hse_doc_studio.core.jobs.scheduler import QueueQuota

KEY_USER_CONCURRENT = "jobs.concurrent"
KEY_ORG_CONCURRENT = "jobs.org_concurrent"
KEY_MAX_DURATION_S = "jobs.max_duration_s"
QUOTA_KEYS = (KEY_USER_CONCURRENT, KEY_ORG_CONCURRENT, KEY_MAX_DURATION_S)

MAX_CONCURRENT = 1000
MIN_DURATION_S = 10
MAX_DURATION_S = 24 * 3600


class QuotaOwnerKind(StrEnum):
    org = "org"
    user = "user"


class QuotaResource(StrEnum):
    """`concurrent_user` на уровне организации задаёт предел каждому её участнику без своего значения."""

    concurrent_user = "jobs.concurrent_user"
    concurrent_org = "jobs.concurrent_org"
    max_duration_s = "jobs.max_duration_s"


@dataclass(frozen=True)
class QuotaOverride:
    owner_kind: QuotaOwnerKind
    owner_id: str
    resource: QuotaResource
    hard_limit: int


class IQuotaOverrideRepository(Protocol):
    async def list_all(self) -> Sequence[QuotaOverride]: ...

    async def set(self, override: QuotaOverride) -> None: ...

    async def delete(self, owner_kind: QuotaOwnerKind, owner_id: str, resource: QuotaResource) -> None: ...


class IProjectOrgReader(Protocol):
    async def org_of(self, project_id: UUID) -> UUID | None:
        """Организация-владелец проекта; `None` у личного проекта и у неизвестного."""
        ...


class IQuotaResolver(Protocol):
    async def current(self) -> QueueQuota | None:
        """Лимиты для выдачи задач; `None` когда ни одного лимита нет."""
        ...

    async def max_duration_s(self, user_id: UUID, org_id: UUID | None) -> float | None:
        """Предельная длительность задачи пользователя: user > org > установка."""
        ...


def org_key(owner_org_id: str) -> UUID:
    """Ключ организации в очереди: `jobs.org_id` это UUID, а владелец проекта хранится строкой."""
    try:
        return UUID(owner_org_id)
    except ValueError:
        return uuid5(NAMESPACE_OID, owner_org_id)


def overrides_to_queue_quota(base: QueueQuota, overrides: Sequence[QuotaOverride]) -> QueueQuota:
    user_caps: dict[UUID, int] = {}
    org_user_caps: dict[UUID, int] = {}
    org_caps: dict[UUID, int] = {}
    for item in overrides:
        if item.owner_kind is QuotaOwnerKind.user:
            try:
                key = UUID(item.owner_id)
            except ValueError:
                continue
            if item.resource is QuotaResource.concurrent_user:
                user_caps[key] = item.hard_limit
        elif item.resource is QuotaResource.concurrent_user:
            org_user_caps[org_key(item.owner_id)] = item.hard_limit
        elif item.resource is QuotaResource.concurrent_org:
            org_caps[org_key(item.owner_id)] = item.hard_limit
    return replace(base, user_caps=user_caps, org_user_caps=org_user_caps, org_caps=org_caps)


def duration_cap(
    default: int | None, overrides: Sequence[QuotaOverride], user_id: UUID, org_id: UUID | None
) -> int | None:
    """Приоритет user > org > установка для предельной длительности."""
    by_owner = {
        (item.owner_kind, org_key(item.owner_id) if item.owner_kind is QuotaOwnerKind.org else item.owner_id): item
        for item in overrides
        if item.resource is QuotaResource.max_duration_s
    }
    own = by_owner.get((QuotaOwnerKind.user, str(user_id)))
    if own is not None:
        return own.hard_limit
    if org_id is not None and (of_org := by_owner.get((QuotaOwnerKind.org, org_id))) is not None:
        return of_org.hard_limit
    return default


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
