"""Таблицы очереди задач: сами задачи, метки справедливости и последние опросы раннеров."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.core.secrets import EncryptedColumn, encrypted_columns
from hse_doc_studio.infra.db.base import Base


class JobRow(Base):
    """Запись очереди. Пользователь, проект и раннер без внешних ключей: порядок их появления не важен."""

    __tablename__ = "jobs"
    __table_args__ = (
        # Порядок выдачи: класс, метка справедливости, время постановки, номер.
        Index(
            "ix_jobs_queued_order",
            "priority_class",
            "vtime",
            "queued_at",
            "seq",
            postgresql_where=text("state = 'queued'"),
        ),
        Index("ix_jobs_running_user", "user_id", postgresql_where=text("state = 'running'")),
        Index("ix_jobs_running_org", "org_id", postgresql_where=text("state = 'running'")),
        Index("ix_jobs_running_runner", "runner_id", postgresql_where=text("state = 'running'")),
        Index("ix_jobs_running_lease", "lease_until", postgresql_where=text("state = 'running'")),
        Index("ix_jobs_queued_coalesce", "coalesce_key", postgresql_where=text("state = 'queued'")),
        Index("ix_jobs_project_id", "project_id"),
        Index(
            "ix_jobs_unapplied",
            "seq",
            postgresql_where=text("applied_at IS NULL AND state IN ('succeeded', 'failed', 'cancelled', 'timed_out')"),
        ),
        CheckConstraint("attempt >= 0 AND max_attempts >= 1", name="attempts"),
        # Маршрут: личные раннеры владельца сначала (окно ожидания) или один конкретный раннер (ретрансляция ИИ).
        Index(
            "ix_jobs_queued_personal",
            "route_owner_id",
            "priority_class",
            "vtime",
            "queued_at",
            "seq",
            postgresql_where=text("state = 'queued' AND route = 'personal_first'"),
        ),
        Index(
            "ix_jobs_queued_pinned", "target_runner_id", postgresql_where=text("state = 'queued' AND route = 'pinned'")
        ),
        # Квоты установки считают только задачи на общих раннерах.
        Index(
            "ix_jobs_running_shared_user",
            "user_id",
            postgresql_where=text("state = 'running' AND runner_scope = 'shared'"),
        ),
        Index(
            "ix_jobs_running_shared_org",
            "org_id",
            postgresql_where=text("state = 'running' AND runner_scope = 'shared'"),
        ),
        CheckConstraint("route IN ('shared', 'personal_first', 'pinned')", name="route"),
        CheckConstraint("(route = 'pinned') = (target_runner_id IS NOT NULL)", name="route_pinned"),
        CheckConstraint(
            "(route = 'personal_first') = (route_owner_id IS NOT NULL AND personal_until IS NOT NULL)",
            name="route_personal",
        ),
        CheckConstraint("runner_scope IS NULL OR runner_scope IN ('shared', 'personal')", name="runner_scope"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    org_id: Mapped[UUID | None] = mapped_column(Uuid)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    priority_class: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    vtime: Mapped[float] = mapped_column(Double, nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_s: Mapped[float] = mapped_column(Double, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    coalesce_key: Mapped[str | None] = mapped_column(String(512))
    affinity_runner_id: Mapped[UUID | None] = mapped_column(Uuid)
    runner_id: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    # Когда итог задачи применён к тому и записи сборки; пусто у терминальной задачи значит «довершить при старте».
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    route: Mapped[str] = mapped_column(String(16), nullable=False, server_default="shared")
    # Хозяин личных раннеров для `personal_first`: владелец проекта на момент постановки.
    route_owner_id: Mapped[str | None] = mapped_column(String(64))
    personal_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_runner_id: Mapped[UUID | None] = mapped_column(Uuid)
    # Кто взял текущую попытку (`shared`/`personal`): пишет сервер при выдаче, не раннер.
    runner_scope: Mapped[str | None] = mapped_column(String(16))
    route_reason: Mapped[str | None] = mapped_column(String(32))
    # Сколько метки справедливости потратила постановка; возвращается при выдаче личному раннеру.
    vcost: Mapped[float] = mapped_column(Double, nullable=False, server_default="1.0")
    timeout_personal_s: Mapped[float | None] = mapped_column(Double)


class FairShareRow(Base):
    """Метка справедливости пользователя; строку блокируют при постановке."""

    __tablename__ = "fair_share"

    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    vtime: Mapped[float | None] = mapped_column(Double)


class JobQueueStateRow(Base):
    """Единственная строка со сквозным временем очереди."""

    __tablename__ = "job_queue_state"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default="1")
    global_vtime: Mapped[float] = mapped_column(Double, nullable=False, server_default="0")


class JobRunnerPollRow(Base):
    """Когда раннер последний раз просил работу и сколько слотов у него есть: по этому решается аффинность."""

    __tablename__ = "job_runner_polls"

    runner_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False)


_OWNER_CHECK = "(owner_kind = 'instance' AND owner_id IS NULL) OR (owner_kind = 'user' AND owner_id IS NOT NULL)"


class RunnerRow(Base):
    """Раннер установки или личный раннер человека. Токен только хешем; создатель и хозяин без внешнего ключа:
    запись переживает удаление человека (его раннеры при удалении отзываются)."""

    __tablename__ = "runners"
    __table_args__ = (
        Index("ix_runners_owner", "owner_kind", "owner_id"),
        CheckConstraint("concurrency >= 1", name="runner_concurrency"),
        CheckConstraint(_OWNER_CHECK, name="owner"),
        CheckConstraint("ai_concurrency >= 0", name="ai_concurrency"),
        CheckConstraint("paused_by IS NULL OR paused_by IN ('owner', 'admin')", name="paused_by"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="instance")
    owner_id: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    resource_class: Mapped[str] = mapped_column(String(32), nullable=False)
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    host_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="cli")
    features: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, server_default="{}")
    # Объявленные ИИ-адреса: `{"name", "flavor"}` без URL.
    ai_endpoints: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    ai_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_seen_ip: Mapped[str | None] = mapped_column(String(64))
    offline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    renamed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Кто поставил на паузу: `owner` или `admin`; паузу админа хозяин не снимает.
    paused_by: Mapped[str | None] = mapped_column(String(16))


class RunnerRegistrationTokenRow(Base):
    __tablename__ = "runner_registration_tokens"
    __table_args__ = (CheckConstraint(_OWNER_CHECK, name="owner"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="instance")
    owner_id: Mapped[str | None] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    uses: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purpose: Mapped[str] = mapped_column(String(16), nullable=False, server_default="manual")


class RunnerPairingRow(Base):
    """Сопряжение по коду устройства: код устройства только хешем, секрет выданного токена шифртекстом до выдачи."""

    __tablename__ = "runner_pairings"
    __table_args__ = (
        Index("ix_runner_pairings_expires_at", "expires_at"),
        CheckConstraint("status IN ('pending', 'approved', 'denied', 'delivered', 'expired')", name="status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_code: Mapped[str] = mapped_column(String(9), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    host_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64))
    token_id: Mapped[str | None] = mapped_column(String(64))
    # Привязка `column_aad("runner_pairings", "token_secret_enc", id)`; стирается при выдаче устройству.
    token_secret_enc: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuotaRow(Base):
    """Переопределение квоты для организации или пользователя; уровень установки живёт в instance_settings."""

    __tablename__ = "quotas"
    __table_args__ = (CheckConstraint("hard_limit >= 1", name="quota_hard_limit"),)

    owner_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource: Mapped[str] = mapped_column(String(32), primary_key=True)
    period: Mapped[str] = mapped_column(String(16), primary_key=True, server_default="none")
    soft_limit: Mapped[int | None] = mapped_column(Integer)
    hard_limit: Mapped[int] = mapped_column(Integer, nullable=False)


encrypted_columns.register(EncryptedColumn("runner_pairings", "token_secret_enc", pk="id"))
