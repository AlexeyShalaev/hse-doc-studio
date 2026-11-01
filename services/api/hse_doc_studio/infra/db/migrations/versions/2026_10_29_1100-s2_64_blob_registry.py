"""blobs и file_hash_cache: реестр блобов входа задач и кэш хешей файлов проекта

Revision ID: s2_64_blob_registry
Revises: s2_60_compile_records
Create Date: 2026-10-29 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s2_64_blob_registry"
down_revision: str | None = "s2_60_compile_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blobs",
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_referenced_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("sha256"),
    )
    op.create_index("ix_blobs_last_referenced_at", "blobs", ["last_referenced_at"])
    op.create_table(
        "file_hash_cache",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "path"),
    )


def downgrade() -> None:
    op.drop_table("file_hash_cache")
    op.drop_index("ix_blobs_last_referenced_at", table_name="blobs")
    op.drop_table("blobs")
