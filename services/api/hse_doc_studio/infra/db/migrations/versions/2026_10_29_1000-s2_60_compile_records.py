"""compile_records: записи сборок документов на сервере

Revision ID: s2_60_compile_records
Revises: s2_55_user_settings
Create Date: 2026-10-29 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "s2_60_compile_records"
down_revision: str | None = "s2_55_user_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compile_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("doc_id", sa.String(length=256), nullable=False),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("actor_name", sa.String(length=256), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("words", sa.Integer(), nullable=True),
        sa.Column("chars", sa.Integer(), nullable=True),
        sa.Column("check_results", JSONB(), server_default="[]", nullable=False),
        sa.Column("log", sa.Text(), server_default="", nullable=False),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compile_records_project_doc_started",
        "compile_records",
        ["project_id", "doc_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_compile_records_unfinished",
        "compile_records",
        ["project_id"],
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("ix_compile_records_unfinished", table_name="compile_records")
    op.drop_index("ix_compile_records_project_doc_started", table_name="compile_records")
    op.drop_table("compile_records")
