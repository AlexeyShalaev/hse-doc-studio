"""Автообновление серверной установки: политика, окно, запуски обновления и их события."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum


class UpdatePolicy(StrEnum):
    off = "off"  # не проверять и не сообщать
    notify = "notify"  # проверять и сообщать админам, ставит человек кнопкой
    auto = "auto"  # ставить сам в окно обслуживания


class MaxBump(StrEnum):
    """Самый крупный шаг версии, который политика `auto` ставит без человека."""

    patch = "patch"
    minor = "minor"


class Verify(StrEnum):
    none = "none"  # без проверки образа: только для закрытых зеркал и форков
    digest = "digest"  # дайджест скачанного образа равен опубликованному в релизе
    cosign = "cosign"  # плюс подпись cosign (keyless, GitHub OIDC) в контейнере cosign


class RunKind(StrEnum):
    update = "update"
    rollback = "rollback"  # ручной возврат на предыдущую версию


class RunTrigger(StrEnum):
    auto = "auto"
    manual = "manual"


class RunStatus(StrEnum):
    waiting_backup = "waiting_backup"  # идёт полный бэкап, исполнителю запуск ещё не отдан
    queued = "queued"  # ждёт, пока апдейтер заберёт
    running = "running"  # апдейтер работает
    succeeded = "succeeded"
    rolled_back = "rolled_back"  # новая версия не поднялась, система вернулась на прежнюю
    failed = "failed"  # откат не удался или апдейтер потерян: нужны руки оператора
    cancelled = "cancelled"  # до начала работ (бэкап не удался, апдейтер молчит, отмена админом)


ACTIVE_STATUSES = frozenset({RunStatus.waiting_backup, RunStatus.queued, RunStatus.running})
TERMINAL_STATUSES = frozenset(set(RunStatus) - ACTIVE_STATUSES)

# Фазы, которые сообщает апдейтер (порядок как в работе).
PHASES = (
    "preflight",
    "snapshot",
    "pull",
    "verify",
    "stop",
    "migrate",
    "restart",
    "health",
    "rollback",
    "restore",
    "finish",
)


@dataclass(frozen=True)
class UpdateSettings:
    policy: UpdatePolicy = UpdatePolicy.notify
    channel: str = "stable"  # другие каналы не публикуются; ключ оставлен под будущее
    max_bump: MaxBump = MaxBump.minor
    # Окно обслуживания в UTC: дни недели (0 = понедельник), начало в минутах от полуночи, длительность в минутах.
    window_days: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
    window_start_min: int = 2 * 60
    window_minutes: int = 180
    backup_first: bool = True
    verify: Verify = Verify.digest
    notify_admins: bool = True


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    date: str = ""
    notes: tuple[str, ...] = ()
    digests_url: str = ""


@dataclass(frozen=True)
class RunEvent:
    seq: int
    at: datetime
    phase: str
    level: str  # info | warn | error
    message: str


@dataclass(frozen=True)
class UpdateRun:
    id: str
    kind: RunKind
    trigger: RunTrigger
    status: RunStatus
    from_version: str
    to_version: str
    created_at: datetime
    phase: str | None = None
    from_revision: str | None = None
    to_revision: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    requested_by: str | None = None
    backup_run_id: str | None = None
    restore_db: bool = False  # ручной откат: админ согласился потерять данные после обновления
    db_restored: bool = False
    digests_url: str = ""
    verify: Verify = Verify.digest
    error_code: str | None = None
    error: str | None = None
    last_seq: int = 0
    events: tuple[RunEvent, ...] = field(default_factory=tuple)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def duration_s(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return max(0.0, (self.finished_at - self.started_at).total_seconds())

    def with_(self, **changes: object) -> UpdateRun:
        return replace(self, **changes)  # type: ignore[arg-type]
