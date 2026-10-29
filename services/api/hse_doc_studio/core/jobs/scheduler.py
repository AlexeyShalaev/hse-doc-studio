"""Чистые правила очереди: справедливое разделение по пользователям, классы, лимиты, склейка, аффинность.

Без ввода-вывода и часов: время и счётчики приходят аргументами, поэтому одни и те же функции
считают порядок и в памяти, и в Postgres, а тесты не поднимают базу.

Справедливость это взвешенная честная очередь по времени старта (start-time fair queuing).
При постановке задача получает `vtime = max(vtime_пользователя, global_vtime) + cost / weight`;
`global_vtime` двигается вперёд до `vtime` взятой задачи. Пользователь с пачкой из 15 сборок получает
метки v+1..v+15, а новичок встаёт на global_vtime+1 и идёт следующим. Правило `max` не даёт
метке пользователя, простоявшего без задач, остаться в прошлом и обогнать всех накопленным кредитом.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from hse_doc_studio.core.jobs.entities import JobSpec, compile_payload_of
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass
from hse_doc_studio.core.jobs.registry import job_kind_spec

# Сколько задача ждёт «своего» раннера, у которого тёплый кэш сборки, прежде чем её может взять любой другой.
AFFINITY_WAIT = timedelta(seconds=2)
# Таймаут, если у вида нет своего значения и квота его не задаёт.
FALLBACK_TIMEOUT_S = 600.0


@dataclass(frozen=True)
class QueueQuota:
    """Лимиты одновременной работы; `None` значит без лимита. Исчерпание означает ожидание в очереди."""

    max_running_per_user: int | None = None
    max_running_per_org: int | None = None
    max_timeout_s: float | None = None
    # Переопределения по владельцам, приоритет user > org > установка. Ключ организации это `jobs.org_id`.
    user_caps: Mapping[UUID, int] = field(default_factory=dict, hash=False)
    org_user_caps: Mapping[UUID, int] = field(default_factory=dict, hash=False)
    org_caps: Mapping[UUID, int] = field(default_factory=dict, hash=False)

    @property
    def is_unlimited(self) -> bool:
        return (
            self.max_running_per_user is None
            and self.max_running_per_org is None
            and self.max_timeout_s is None
            and not (self.user_caps or self.org_user_caps or self.org_caps)
        )

    def user_cap(self, user_id: UUID, org_id: UUID | None) -> int | None:
        """Сколько задач пользователя могут идти разом: своё значение, затем организации, затем установки."""
        if user_id in self.user_caps:
            return self.user_caps[user_id]
        if org_id is not None and org_id in self.org_user_caps:
            return self.org_user_caps[org_id]
        return self.max_running_per_user

    def org_cap(self, org_id: UUID | None) -> int | None:
        if org_id is not None and org_id in self.org_caps:
            return self.org_caps[org_id]
        return self.max_running_per_org

    def __post_init__(self) -> None:
        for name in ("max_running_per_user", "max_running_per_org"):
            limit = getattr(self, name)
            if limit is not None and limit < 1:
                raise ValueError(f"{name} must be at least 1")
        if self.max_timeout_s is not None and self.max_timeout_s <= 0:
            raise ValueError("max_timeout_s must be positive")
        for caps in (self.user_caps, self.org_user_caps, self.org_caps):
            if any(limit < 1 for limit in caps.values()):
                raise ValueError("per-owner caps must be at least 1")


def priority_class_of(kind: JobKind) -> JobPriorityClass:
    return job_kind_spec(kind).policy.priority_class


def max_attempts_of(kind: JobKind) -> int:
    return job_kind_spec(kind).policy.max_attempts


def assign_vtime(user_vtime: float | None, global_vtime: float, cost: float = 1.0, weight: float = 1.0) -> float:
    """Метка новой задачи пользователя; `user_vtime=None` у того, у кого ещё не было задач."""
    if cost <= 0 or weight <= 0:
        raise ValueError("cost and weight must be positive")
    start = global_vtime if user_vtime is None else max(user_vtime, global_vtime)
    return start + cost / weight


def advance_global_vtime(global_vtime: float, claimed_vtime: float) -> float:
    """Глобальное время не откатывается: берётся метка последней взятой задачи, если она больше."""
    return max(global_vtime, claimed_vtime)


def coalesce_key(project_id: UUID, kind: JobKind, doc_id: str) -> str:
    return f"{project_id}:{kind.value}:{doc_id}"


def coalesce_key_of(spec: JobSpec) -> str | None:
    """Ключ склейки: у сборки это проект и документ, остальные виды не склеиваются."""
    if spec.kind is not JobKind.compile:
        return None
    return coalesce_key(spec.project_id, spec.kind, compile_payload_of(spec).doc_id)


def caps_allow(
    running_of_user: int,
    running_of_org: int | None,
    quota: QueueQuota,
    *,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
) -> bool:
    """Можно ли ещё одну задачу пользователя; `running_of_org=None` когда пользователь вне организации."""
    user_cap = quota.user_cap(user_id, org_id) if user_id is not None else quota.max_running_per_user
    if user_cap is not None and running_of_user >= user_cap:
        return False
    org_cap = quota.org_cap(org_id)
    return not (org_cap is not None and running_of_org is not None and running_of_org >= org_cap)


def resolve_timeout(kind: JobKind, quota: QueueQuota | None = None) -> float:
    """Таймаут вида, урезанный квотой, если она строже."""
    timeout = job_kind_spec(kind).policy.default_timeout_s or FALLBACK_TIMEOUT_S
    if quota is not None and quota.max_timeout_s is not None:
        return min(timeout, quota.max_timeout_s)
    return timeout


def affinity_allows(
    affinity_runner_id: UUID | None,
    queued_at: datetime,
    runner_id: UUID,
    now: datetime,
    *,
    affine_available: bool,
) -> bool:
    """Может ли этот раннер взять задачу, закреплённую за другим.

    `affine_available` значит, что закреплённый раннер жив и у него есть свободный слот: пока это так,
    остальные ждут `AFFINITY_WAIT`, чтобы не терять тёплый кэш сборки.
    """
    if affinity_runner_id is None or affinity_runner_id == runner_id:
        return True
    return not affine_available or now - queued_at >= AFFINITY_WAIT


def retry_available(attempt: int, max_attempts: int) -> bool:
    """Осталась ли попытка после потери раннера."""
    return attempt < max_attempts
