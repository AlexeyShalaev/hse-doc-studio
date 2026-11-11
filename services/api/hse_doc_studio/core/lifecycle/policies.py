"""Реестр политик жизненного цикла данных: что в установке растёт само и как это ограничено.

Реестр один на всё приложение. Каждый источник роста описан здесь: где живёт, чем ограничен, можно ли менять срок
хранения из админки и в каких пределах. Нижние границы защищают журнал аудита и учёт безопасности от случайного
«хранить час». Сами очистки лежат в infra и подключаются к ключам реестра.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

KEY_PREFIX = "retention."


class Group(StrEnum):
    database = "database"
    objects = "objects"
    disk = "disk"
    logs = "logs"


class Strategy(StrEnum):
    partition_drop = "partition_drop"  # партиции Postgres по месяцам: старая партиция отбрасывается целиком
    delete_batches = "delete_batches"  # DELETE пачками по индексу времени
    file_sweep = "file_sweep"  # файлы старше срока на диске
    own_task = "own_task"  # чистит собственная периодическая задача (показываем её итог)
    on_write = "on_write"  # предел держится при записи (сколько последних записей хранить)
    infra = "infra"  # ограничено инфраструктурой, не приложением (ротация логов контейнеров, WAL)


@dataclass(frozen=True)
class RetentionBounds:
    default_days: int
    min_days: int
    max_days: int

    def contains(self, days: int) -> bool:
        return self.min_days <= days <= self.max_days


@dataclass(frozen=True)
class LifecyclePolicy:
    key: str
    group: Group
    strategy: Strategy
    # None: срок зашит в код (фиксирован) либо предел другого рода (число записей, размер файла).
    bounds: RetentionBounds | None = None
    tables: tuple[str, ...] = ()
    # Периодическая задача, которая чистит источник сама (для own_task): имя в раннере фоновых задач.
    task: str | None = None
    # Можно ли запустить очистку по кнопке. Журнал аудита и учёт безопасности вручную не чистят.
    run_now: bool = True
    # Защищённые источники: срок нельзя снять совсем (только поднять до верхней границы).
    protected: bool = False
    # Переменная окружения, из которой берётся умолчание (для справки и сводки).
    env: str | None = None
    # Растёт ли источник с работой людей: подсказка админке, на что смотреть в первую очередь.
    growth: str = "low"

    @property
    def setting_key(self) -> str | None:
        return f"{KEY_PREFIX}{self.key}_days" if self.bounds is not None else None

    @property
    def editable(self) -> bool:
        return self.bounds is not None and self.strategy in _EDITABLE


_EDITABLE = frozenset({Strategy.partition_drop, Strategy.delete_batches, Strategy.file_sweep})

D = 1
YEAR = 365

POLICIES: tuple[LifecyclePolicy, ...] = (
    LifecyclePolicy(
        "audit_log",
        Group.database,
        Strategy.partition_drop,
        RetentionBounds(YEAR, 90, 10 * YEAR),
        tables=("audit_log",),
        run_now=False,
        protected=True,
        env="HSE_STUDIO__SERVER__AUDIT_RETENTION_DAYS",
        growth="high",
    ),
    LifecyclePolicy(
        "ai_usage",
        Group.database,
        Strategy.partition_drop,
        RetentionBounds(90, 30, 5 * YEAR),
        tables=("ai_usage",),
        env="HSE_STUDIO__AI_GATEWAY__USAGE_RETENTION_DAYS",
        growth="high",
    ),
    LifecyclePolicy(
        "jobs",
        Group.database,
        Strategy.delete_batches,
        RetentionBounds(30, 1, YEAR),
        tables=("jobs",),
        env="HSE_STUDIO__SERVER__JOB_RETENTION_DAYS",
        growth="high",
    ),
    LifecyclePolicy(
        "notifications",
        Group.database,
        Strategy.delete_batches,
        RetentionBounds(90, 14, 2 * YEAR),
        tables=("notifications",),
        growth="medium",
    ),
    # Журнал писем (mail-log.md, L12): строка на попытку отправки, около 1 КБ, растёт как уведомления.
    LifecyclePolicy(
        "mail_log",
        Group.database,
        Strategy.delete_batches,
        RetentionBounds(90, 14, 2 * YEAR),
        tables=("mail_log",),
        growth="medium",
    ),
    LifecyclePolicy(
        "collab_requests",
        Group.database,
        Strategy.delete_batches,
        RetentionBounds(90, 30, 2 * YEAR),
        tables=("project_invitations", "access_requests", "project_transfers"),
        growth="low",
    ),
    LifecyclePolicy(
        "share_links",
        Group.database,
        Strategy.delete_batches,
        RetentionBounds(180, 30, 3 * YEAR),
        tables=("share_links", "share_link_visits", "share_link_grants"),
        growth="low",
    ),
    LifecyclePolicy(
        "guest_sessions",
        Group.database,
        Strategy.delete_batches,
        tables=("guest_sessions", "guest_session_links"),
        growth="medium",
    ),
    LifecyclePolicy(
        "collab_state",
        Group.disk,
        Strategy.file_sweep,
        RetentionBounds(90, 7, YEAR),
        growth="medium",
    ),
    LifecyclePolicy(
        "auth_records",
        Group.database,
        Strategy.own_task,
        tables=("sessions", "auth_tokens", "mail_outbox", "login_attempts", "device_authorizations", "runner_pairings"),
        task="auth_cleanup",
        growth="medium",
    ),
    LifecyclePolicy(
        "deleted_projects",
        Group.disk,
        Strategy.own_task,
        tables=("projects",),
        task="project_purge",
        env="HSE_STUDIO__SERVER__PROJECT_RETENTION_DAYS",
        growth="medium",
    ),
    LifecyclePolicy(
        "blobs", Group.objects, Strategy.own_task, tables=("blobs", "file_hash_cache"), task="blob_gc", growth="high"
    ),
    LifecyclePolicy("orphans", Group.objects, Strategy.own_task, task="orphan_gc", growth="low"),
    LifecyclePolicy(
        "usage_counters", Group.database, Strategy.own_task, tables=("usage_counters",), task="quota_housekeeping"
    ),
    # Команды раннерам (storage-cleanup.md, S13): 20 последних на раннер, старые стираются при вставке.
    LifecyclePolicy("runner_commands", Group.database, Strategy.on_write, tables=("runner_commands",)),
    LifecyclePolicy("compile_records", Group.database, Strategy.on_write, tables=("compile_records",), growth="high"),
    LifecyclePolicy("project_artifacts", Group.objects, Strategy.on_write, tables=("project_artifacts",)),
    LifecyclePolicy("chat_history", Group.database, Strategy.on_write, tables=("chat_messages", "chat_agent_runs")),
    # Прогоны «Освободить место» (storage-cleanup.md, S13): 20 последних, старые стираются при вставке.
    LifecyclePolicy("lifecycle_sweeps", Group.database, Strategy.on_write, tables=("lifecycle_sweeps",)),
    LifecyclePolicy("container_logs", Group.logs, Strategy.infra, growth="high"),
    LifecyclePolicy("process_logs", Group.logs, Strategy.infra),
    LifecyclePolicy("postgres_wal", Group.logs, Strategy.infra),
)

POLICY_BY_KEY: Mapping[str, LifecyclePolicy] = {p.key: p for p in POLICIES}


def effective_days(
    policy: LifecyclePolicy, stored: Mapping[str, object], default_days: int | None = None
) -> int | None:
    """Срок хранения в днях: правка админа, иначе умолчание окружения, иначе умолчание реестра.

    Правка вне допустимых границ (например, из старой версии) не действует: берётся умолчание. Умолчание окружения
    0 значит «хранить без срока» (так было у `audit_retention_days`): `None` у вызывающего означает «не очищать».
    """
    bounds = policy.bounds
    if bounds is None or policy.setting_key is None:
        return None
    raw = stored.get(policy.setting_key)
    if isinstance(raw, int) and not isinstance(raw, bool) and bounds.contains(raw):
        return raw
    if default_days is None:
        return bounds.default_days
    if default_days == 0:
        return None
    return min(max(default_days, bounds.min_days), bounds.max_days)
