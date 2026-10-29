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
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

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


class RunnerRow(Base):
    """Раннер установки. Токен только хешем; создатель без внешнего ключа: запись переживает удаление человека."""

    __tablename__ = "runners"
    __table_args__ = (
        Index("ix_runners_owner", "owner_kind", "owner_id"),
        CheckConstraint("concurrency >= 1", name="runner_concurrency"),
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


class RunnerRegistrationTokenRow(Base):
    __tablename__ = "runner_registration_tokens"

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
