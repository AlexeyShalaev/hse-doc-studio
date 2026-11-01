"""git_host_settings, git_known_hosts: доверие к git-серверам на уровне установки

Revision ID: s2_62_git_trust
Revises: s2_61_git_credentials
Create Date: 2026-10-30 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s2_62_git_trust"
down_revision: str | None = "s2_61_git_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "git_host_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("provider_override", sa.String(length=32), nullable=True),
        sa.Column("ca_pem", sa.Text(), nullable=True),
        sa.Column("pinned_fingerprint", sa.Text(), nullable=True),
        sa.Column("pinned_pem", sa.Text(), nullable=True),
        sa.Column("detected", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "git_known_hosts",
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("key_type", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("trusted_by", sa.String(length=64), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["trusted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("pattern", "key_type", "fingerprint"),
    )


def downgrade() -> None:
    op.drop_table("git_known_hosts")
    op.drop_table("git_host_settings")
