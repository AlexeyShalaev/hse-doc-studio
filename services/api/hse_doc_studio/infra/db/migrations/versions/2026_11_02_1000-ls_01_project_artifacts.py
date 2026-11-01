"""project_artifacts: PDF, выгруженные локальной Студией после её сборки

Revision ID: ls_01_project_artifacts
Revises: cf_01g_git_remote
Create Date: 2026-11-02 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ls_01_project_artifacts"
down_revision: str | None = "cf_01g_git_remote"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("doc_id", sa.String(length=128), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("source_commit", sa.String(length=64), nullable=True),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_by", sa.String(length=64), nullable=True),
        sa.Column("uploaded_by_name", sa.String(length=256), nullable=True),
        sa.Column("client_name", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('pdf')", name=op.f("ck_project_artifacts_kind")),
    )
    op.create_index(
        "ix_project_artifacts_project_doc_uploaded",
        "project_artifacts",
        ["project_id", "doc_id", sa.text("uploaded_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_project_artifacts_project_doc_uploaded", table_name="project_artifacts")
    op.drop_table("project_artifacts")
