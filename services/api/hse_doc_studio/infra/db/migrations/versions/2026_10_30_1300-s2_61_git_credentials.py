"""git_credentials, git_remote_bindings: git-доступы пользователей и привязка доступа к проекту

Revision ID: s2_61_git_credentials
Revises: s2_57_signing_identities
Create Date: 2026-10-30 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s2_61_git_credentials"
down_revision: str | None = "s2_57_signing_identities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "git_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("token_family", sa.Text(), nullable=True),
        sa.Column("public_key", sa.Text(), nullable=True),
        sa.Column("fingerprint_sha256", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("secret_enc", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_git_credentials_owner", "git_credentials", ["owner_id", "created_at"])
    op.create_table(
        "git_remote_bindings",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=False),
        sa.Column("bound_by", sa.String(length=64), nullable=True),
        sa.Column("scheme", sa.String(length=8), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credential_id"], ["git_credentials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bound_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_index("ix_git_remote_bindings_credential", "git_remote_bindings", ["credential_id"])


def downgrade() -> None:
    op.drop_index("ix_git_remote_bindings_credential", table_name="git_remote_bindings")
    op.drop_table("git_remote_bindings")
    op.drop_index("ix_git_credentials_owner", table_name="git_credentials")
    op.drop_table("git_credentials")
