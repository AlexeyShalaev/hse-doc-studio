"""Сущности самодиагностики: статус, реестр проверок, вердикт и результат одной проверки."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum

Values = Mapping[str, str | int | float]

# Причины, при которых проверка «не применима» (подсистема не настроена): статус ok, на экране приглушённая строка.
NOT_APPLICABLE_REASONS = frozenset({"not_configured", "no_tls", "disabled"})


class DiagStatus(IntEnum):
    ok = 0
    warn = 1
    fail = 2


class CheckGroup(StrEnum):
    data = "data"
    compute = "compute"
    security = "security"
    operations = "operations"


class CheckId(StrEnum):
    database = "database"
    migrations = "migrations"
    object_storage = "object_storage"
    runners = "runners"
    jobs = "jobs"
    disk = "disk"
    tls_public = "tls_public"
    tls_s3 = "tls_s3"
    backups = "backups"
    smtp = "smtp"
    scheduler = "scheduler"


@dataclass(frozen=True)
class CheckSpec:
    id: CheckId
    group: CheckGroup


# Порядок реестра это порядок на экране.
CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec(CheckId.database, CheckGroup.data),
    CheckSpec(CheckId.migrations, CheckGroup.data),
    CheckSpec(CheckId.object_storage, CheckGroup.data),
    CheckSpec(CheckId.disk, CheckGroup.data),
    CheckSpec(CheckId.runners, CheckGroup.compute),
    CheckSpec(CheckId.jobs, CheckGroup.compute),
    CheckSpec(CheckId.scheduler, CheckGroup.compute),
    CheckSpec(CheckId.tls_public, CheckGroup.security),
    CheckSpec(CheckId.tls_s3, CheckGroup.security),
    CheckSpec(CheckId.backups, CheckGroup.operations),
    CheckSpec(CheckId.smtp, CheckGroup.operations),
)
CHECK_BY_ID: dict[str, CheckSpec] = {spec.id.value: spec for spec in CHECKS}


@dataclass(frozen=True)
class Verdict:
    """Итог правил по фактам: код причины для словаря интерфейса и числа для подстановки (без секретов)."""

    status: DiagStatus
    reason: str
    values: Values = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    """Результат одной проверки. `hint` это код подсказки «что делать»: есть, пока статус не ok."""

    check_id: str
    status: DiagStatus
    reason: str
    values: Values
    checked_at: datetime
    duration_ms: int

    @property
    def hint(self) -> str | None:
        return None if self.status is DiagStatus.ok else self.reason

    @property
    def applicable(self) -> bool:
        return not (self.status is DiagStatus.ok and self.reason in NOT_APPLICABLE_REASONS)


def overall(results: list[CheckResult]) -> DiagStatus:
    """Общий итог: худший статус применимых проверок."""
    return max((r.status for r in results), default=DiagStatus.ok)
