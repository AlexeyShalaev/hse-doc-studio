"""Виды квотируемых ресурсов и границы их периодов.

Место и участники не копятся счётчиком (их считают по таблицам проектов), сборки и токены ИИ копятся в
`usage_counters` по началу периода: новый период это новая строка, поэтому сброс не требует расписания.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum

from hse_doc_studio.core.jobs.quotas import QuotaResource


class QuotaKind(StrEnum):
    storage = "storage"
    builds = "builds"
    ai_tokens_day = "ai_tokens_day"
    ai_tokens_month = "ai_tokens_month"
    members = "members"


class Period(StrEnum):
    none = "none"
    day = "day"
    month = "month"


class QuotaScope(StrEnum):
    """`user`: предел на одного человека. `org`: общий потолок организации."""

    user = "user"
    org = "org"


@dataclass(frozen=True)
class KindSpec:
    kind: QuotaKind
    period: Period
    unit: str
    # Копится ли расход счётчиком; место и участников считают по таблицам.
    counted: bool
    user_resource: QuotaResource
    org_resource: QuotaResource

    def resource(self, scope: QuotaScope) -> QuotaResource:
        return self.user_resource if scope is QuotaScope.user else self.org_resource


KIND_SPECS: dict[QuotaKind, KindSpec] = {
    QuotaKind.storage: KindSpec(
        QuotaKind.storage, Period.none, "bytes", False, QuotaResource.storage_user, QuotaResource.storage_org
    ),
    QuotaKind.builds: KindSpec(
        QuotaKind.builds, Period.month, "builds", True, QuotaResource.builds_user, QuotaResource.builds_org
    ),
    QuotaKind.ai_tokens_day: KindSpec(
        QuotaKind.ai_tokens_day, Period.day, "tokens", True, QuotaResource.ai_day_user, QuotaResource.ai_day_org
    ),
    QuotaKind.ai_tokens_month: KindSpec(
        QuotaKind.ai_tokens_month, Period.month, "tokens", True, QuotaResource.ai_month_user, QuotaResource.ai_month_org
    ),
    QuotaKind.members: KindSpec(
        QuotaKind.members, Period.none, "members", False, QuotaResource.members_user, QuotaResource.members_org
    ),
}

COUNTED_KINDS = tuple(kind for kind, spec in KIND_SPECS.items() if spec.counted)

# Сколько месяцев строки счётчиков хранятся после конца периода.
COUNTER_RETENTION_DAYS = 13 * 31


def period_start(period: Period, now: datetime) -> date | None:
    """Начало периода по UTC; у вида без периода `None`."""
    moment = now.astimezone(timezone.utc)
    if period is Period.day:
        return moment.date()
    if period is Period.month:
        return moment.date().replace(day=1)
    return None


def period_end(period: Period, now: datetime) -> datetime | None:
    """Момент сброса: начало следующих суток или следующего месяца по UTC."""
    start = period_start(period, now)
    if start is None:
        return None
    if period is Period.day:
        nxt = start + timedelta(days=1)
    else:
        nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return datetime(nxt.year, nxt.month, nxt.day, tzinfo=timezone.utc)
