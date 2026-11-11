"""lifecycle_sweeps: прогоны «Освободить место» (storage-cleanup.md, 5.4 и 5.5)

Revision ID: dk_02_lifecycle_sweeps
Revises: sr_10_new_version_kind
Create Date: 2026-11-16 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dk_02_lifecycle_sweeps"
down_revision: str | None = "sr_10_new_version_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lifecycle_sweeps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_by", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "steps", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('running', 'cancelling', 'done', 'cancelled', 'error', 'interrupted')",
            name=op.f("ck_lifecycle_sweeps_status"),
        ),
        sa.ForeignKeyConstraint(
            ["started_by"], ["users.id"], name=op.f("fk_lifecycle_sweeps_started_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lifecycle_sweeps")),
    )
    op.create_index("ix_lifecycle_sweeps_started", "lifecycle_sweeps", [sa.text("started_at DESC")])
    op.create_index(
        "uq_lifecycle_sweeps_active",
        "lifecycle_sweeps",
        [sa.text("(true)")],
        unique=True,
        postgresql_where=sa.text("status IN ('running', 'cancelling')"),
    )


def downgrade() -> None:
    op.drop_index("uq_lifecycle_sweeps_active", table_name="lifecycle_sweeps")
    op.drop_index("ix_lifecycle_sweeps_started", table_name="lifecycle_sweeps")
    op.drop_table("lifecycle_sweeps")
