"""runners и runner_registration_tokens: реестр раннеров и токены регистрации

Revision ID: s2_73_runners
Revises: s2_72_jobs_started_at
Create Date: 2026-10-28 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s2_73_runners"
down_revision: str | None = "s2_72_jobs_started_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runners",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_kind", sa.String(length=16), server_default="instance", nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("resource_class", sa.String(length=32), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("paused", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("concurrency >= 1", name=op.f("ck_runners_runner_concurrency")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runners")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_runners_token_hash")),
    )
    op.create_index("ix_runners_owner", "runners", ["owner_kind", "owner_id"])
    op.create_table(
        "runner_registration_tokens",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_kind", sa.String(length=16), server_default="instance", nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=128), server_default="", nullable=False),
        sa.Column("max_uses", sa.Integer(), server_default="1", nullable=False),
        sa.Column("uses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runner_registration_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_runner_registration_tokens_token_hash")),
    )


def downgrade() -> None:
    op.drop_table("runner_registration_tokens")
    op.drop_index("ix_runners_owner", table_name="runners")
    op.drop_table("runners")
