"""quotas: переопределения квот задач для организаций и пользователей

Revision ID: s2_83_quotas
Revises: s2_78_jobs_applied_at
Create Date: 2026-10-30 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s2_83_quotas"
down_revision: str | None = "s2_78_jobs_applied_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quotas",
        sa.Column("owner_kind", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("resource", sa.String(length=32), nullable=False),
        sa.Column("period", sa.String(length=16), server_default="none", nullable=False),
        sa.Column("soft_limit", sa.Integer(), nullable=True),
        sa.Column("hard_limit", sa.Integer(), nullable=False),
        sa.CheckConstraint("hard_limit >= 1", name=op.f("ck_quotas_quota_hard_limit")),
        sa.PrimaryKeyConstraint("owner_kind", "owner_id", "resource", "period", name=op.f("pk_quotas")),
    )


def downgrade() -> None:
    op.drop_table("quotas")
