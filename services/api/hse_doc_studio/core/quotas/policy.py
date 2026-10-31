"""Умолчания установки, разрешение предела (user > org > установка) и оценка использования."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.jobs.quotas import QuotaOverride, QuotaOwnerKind, QuotaResource, org_key, user_key
from hse_doc_studio.core.quotas.kinds import KIND_SPECS, QuotaKind, QuotaScope

KEY_WARN_PERCENT = "quota.warn_percent"
KEY_ON_EXCEED = "quota.on_exceed"
DEFAULT_WARN_PERCENT = 80
MAX_LIMIT = 2**62


def limit_key(kind: QuotaKind, scope: QuotaScope) -> str:
    return f"quota.{kind.value}.{scope.value}"


class OnExceed(StrEnum):
    """Что делать с запросом сверх предела. `deprioritize` относится к сборкам; для остальных он равен `reject`."""

    deprioritize = "deprioritize"
    reject = "reject"
    warn = "warn"


class LimitSource(StrEnum):
    user = "user"
    org = "org"
    installation = "installation"


class QuotaState(StrEnum):
    unlimited = "unlimited"
    ok = "ok"
    warning = "warning"
    exceeded = "exceeded"


@dataclass(frozen=True)
class QuotaPolicy:
    """Значения установки: `limits[(kind, scope)]`, `None` значит без предела."""

    limits: Mapping[tuple[QuotaKind, QuotaScope], int | None] = field(default_factory=dict, hash=False)
    warn_percent: int = DEFAULT_WARN_PERCENT
    on_exceed: OnExceed = OnExceed.deprioritize

    def __post_init__(self) -> None:
        if not 1 <= self.warn_percent <= 100:  # noqa: PLR2004 — проценты
            raise QuotaPolicyError("warn_percent")
        for (kind, scope), value in self.limits.items():
            if value is not None and not 1 <= value <= MAX_LIMIT:
                raise QuotaPolicyError(limit_key(kind, scope))

    def default(self, kind: QuotaKind, scope: QuotaScope) -> int | None:
        return self.limits.get((kind, scope))


class QuotaPolicyError(ValueError):
    """Значение умолчания вне допустимого; `field` называет поле запроса."""

    def __init__(self, field: str) -> None:
        super().__init__(f"quota value out of range: {field}")
        self.field = field


def _positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else None


def policy_from(values: Mapping[str, object]) -> QuotaPolicy:
    """Испорченное значение в базе читается как «без предела» и не останавливает работу."""
    limits: dict[tuple[QuotaKind, QuotaScope], int | None] = {}
    for kind in KIND_SPECS:
        for scope in QuotaScope:
            value = _positive_int(values.get(limit_key(kind, scope)))
            if value is not None and value <= MAX_LIMIT:
                limits[(kind, scope)] = value
    warn = values.get(KEY_WARN_PERCENT)
    warn_percent = (
        warn if isinstance(warn, int) and not isinstance(warn, bool) and 1 <= warn <= 100 else DEFAULT_WARN_PERCENT
    )  # noqa: PLR2004
    raw_mode = values.get(KEY_ON_EXCEED)
    on_exceed = OnExceed(raw_mode) if isinstance(raw_mode, str) and raw_mode in OnExceed else OnExceed.deprioritize
    return QuotaPolicy(limits=limits, warn_percent=warn_percent, on_exceed=on_exceed)


@dataclass(frozen=True)
class OverrideIndex:
    """Переопределения, разложенные по владельцу: поиск без обхода списка и в любом написании UUID."""

    by_user: Mapping[tuple[QuotaResource, UUID], int] = field(default_factory=dict, hash=False)
    by_org: Mapping[tuple[QuotaResource, UUID], int] = field(default_factory=dict, hash=False)

    @classmethod
    def build(cls, overrides: Sequence[QuotaOverride]) -> OverrideIndex:
        users: dict[tuple[QuotaResource, UUID], int] = {}
        orgs: dict[tuple[QuotaResource, UUID], int] = {}
        for item in overrides:
            if item.owner_kind is QuotaOwnerKind.org:
                orgs[(item.resource, org_key(item.owner_id))] = item.hard_limit
            elif (key := user_key(item.owner_id)) is not None:
                users[(item.resource, key)] = item.hard_limit
        return cls(users, orgs)


@dataclass(frozen=True)
class ResolvedLimit:
    hard: int
    source: LimitSource


def resolve_user_limit(
    kind: QuotaKind, user_id: UUID, org_id: UUID | None, policy: QuotaPolicy, overrides: OverrideIndex
) -> ResolvedLimit | None:
    """Предел на человека: своё значение, затем «на участника» его организации, затем установки."""
    resource = KIND_SPECS[kind].resource(QuotaScope.user)
    if (own := overrides.by_user.get((resource, user_id))) is not None:
        return ResolvedLimit(own, LimitSource.user)
    if org_id is not None and (of_org := overrides.by_org.get((resource, org_id))) is not None:
        return ResolvedLimit(of_org, LimitSource.org)
    default = policy.default(kind, QuotaScope.user)
    return ResolvedLimit(default, LimitSource.installation) if default is not None else None


def resolve_org_limit(
    kind: QuotaKind, org_id: UUID, policy: QuotaPolicy, overrides: OverrideIndex
) -> ResolvedLimit | None:
    """Общий потолок организации: своё значение, затем умолчание установки на организацию."""
    resource = KIND_SPECS[kind].resource(QuotaScope.org)
    if (own := overrides.by_org.get((resource, org_id))) is not None:
        return ResolvedLimit(own, LimitSource.org)
    default = policy.default(kind, QuotaScope.org)
    return ResolvedLimit(default, LimitSource.installation) if default is not None else None


def state_of(used: int, limit: int | None, warn_percent: int) -> QuotaState:
    if limit is None:
        return QuotaState.unlimited
    if used >= limit:
        return QuotaState.exceeded
    if used * 100 >= limit * warn_percent:
        return QuotaState.warning
    return QuotaState.ok


@dataclass(frozen=True)
class Assessment:
    """Использование одного вида на одном уровне: чей счётчик, сколько израсходовано и до какого предела."""

    kind: QuotaKind
    scope: QuotaScope
    owner_id: str
    used: int
    limit: int | None
    source: LimitSource | None
    state: QuotaState
    resets_at: datetime | None

    @property
    def percent(self) -> int | None:
        if self.limit is None:
            return None
        return min(100, used_percent(self.used, self.limit))

    def would_exceed(self, amount: int) -> bool:
        return self.limit is not None and self.used + amount > self.limit


def used_percent(used: int, limit: int) -> int:
    return (used * 100) // limit if limit else 100
