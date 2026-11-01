"""quotas_gateway: счётчики расхода по периодам, журнал ИИ-шлюза, точные пределы квот

Revision ID: s6_01_quotas_gateway
Revises: ls_01_project_artifacts
Create Date: 2026-11-03 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s6_01_quotas_gateway"
down_revision: str | None = "ls_01_project_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Байты и токены не влезают в 32 бита; менять тип нельзя (expand/contract), поэтому точное значение рядом.
    op.add_column("quotas", sa.Column("hard_limit_big", sa.BigInteger(), nullable=True))
    op.create_table(
        "usage_counters",
        sa.Column("owner_kind", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("resource", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("used", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("owner_kind", "owner_id", "resource", "period_start", name=op.f("pk_usage_counters")),
    )
    op.create_index("ix_usage_counters_period", "usage_counters", ["resource", "period_start"])
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("provider_owner", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("input_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("counted", sa.Boolean(), server_default="false", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage")),
    )
    op.create_index("ix_ai_usage_at", "ai_usage", ["at"])
    op.create_index("ix_ai_usage_user_at", "ai_usage", ["user_id", "at"])
    op.create_index("ix_ai_usage_provider_at", "ai_usage", ["provider_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_provider_at", table_name="ai_usage")
    op.drop_index("ix_ai_usage_user_at", table_name="ai_usage")
    op.drop_index("ix_ai_usage_at", table_name="ai_usage")
    op.drop_table("ai_usage")
    op.drop_index("ix_usage_counters_period", table_name="usage_counters")
    op.drop_table("usage_counters")
    op.drop_column("quotas", "hard_limit_big")
