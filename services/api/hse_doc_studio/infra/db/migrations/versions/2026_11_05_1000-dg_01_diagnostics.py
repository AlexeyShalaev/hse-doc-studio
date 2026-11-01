"""diag_checks: последний результат и серия статусов каждой проверки самодиагностики

Revision ID: dg_01_diagnostics
Revises: bk_01_backups
Create Date: 2026-11-05 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dg_01_diagnostics"
down_revision: str | None = "bk_01_backups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diag_checks",
        sa.Column("check_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("values", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("streak", sa.Integer(), server_default="1", nullable=False),
        sa.Column("notified_status", sa.SmallInteger(), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN (0, 1, 2)", name=op.f("ck_diag_checks_status")),
        sa.PrimaryKeyConstraint("check_id", name=op.f("pk_diag_checks")),
    )


def downgrade() -> None:
    op.drop_table("diag_checks")
