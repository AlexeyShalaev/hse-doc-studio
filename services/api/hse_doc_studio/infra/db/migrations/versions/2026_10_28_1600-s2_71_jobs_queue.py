"""jobs, fair_share, job_queue_state, job_runner_polls: очередь задач на Postgres

Revision ID: s2_71_jobs_queue
Revises: 0007
Create Date: 2026-10-28 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s2_71_jobs_queue"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("priority_class", sa.SmallInteger(), nullable=False),
        sa.Column("vtime", sa.Double(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("timeout_s", sa.Double(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("coalesce_key", sa.String(length=512), nullable=True),
        sa.Column("affinity_runner_id", sa.Uuid(), nullable=True),
        sa.Column("runner_id", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint("attempt >= 0 AND max_attempts >= 1", name=op.f("ck_jobs_attempts")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("seq", name=op.f("uq_jobs_seq")),
    )
    op.create_index(
        "ix_jobs_queued_order",
        "jobs",
        ["priority_class", "vtime", "queued_at", "seq"],
        unique=False,
        postgresql_where=sa.text("state = 'queued'"),
    )
    for name, column in (("user", "user_id"), ("org", "org_id"), ("runner", "runner_id"), ("lease", "lease_until")):
        op.create_index(
            f"ix_jobs_running_{name}",
            "jobs",
            [column],
            unique=False,
            postgresql_where=sa.text("state = 'running'"),
        )
    op.create_index(
        "ix_jobs_queued_coalesce",
        "jobs",
        ["coalesce_key"],
        unique=False,
        postgresql_where=sa.text("state = 'queued'"),
    )
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"], unique=False)
    op.create_table(
        "fair_share",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("vtime", sa.Double(), nullable=True),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_fair_share")),
    )
    op.create_table(
        "job_queue_state",
        sa.Column("id", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("global_vtime", sa.Double(), server_default="0", nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_job_queue_state_single_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_queue_state")),
    )
    op.execute("INSERT INTO job_queue_state (id, global_vtime) VALUES (1, 0)")
    op.create_table(
        "job_runner_polls",
        sa.Column("runner_id", sa.Uuid(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("runner_id", name=op.f("pk_job_runner_polls")),
    )


def downgrade() -> None:
    op.drop_table("job_runner_polls")
    op.drop_table("job_queue_state")
    op.drop_table("fair_share")
    op.drop_table("jobs")
