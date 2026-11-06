"""runner_ssh_credentials: сохранённые SSH-доступы установки раннеров (секрет шифртекстом)

Revision ID: ri_01_runner_ssh_credentials
Revises: cf_01_compile_failure
Create Date: 2026-11-10 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ri_01_runner_ssh_credentials"
down_revision: str | None = "cf_01_compile_failure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runner_ssh_credentials",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("sudo", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("auth_kind", sa.String(length=16), nullable=False),
        sa.Column("host_key_type", sa.String(length=64), nullable=False),
        sa.Column("host_key_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("host_key_public", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runner_name", sa.String(length=64), nullable=True),
        sa.Column("secret_enc", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runner_ssh_credentials")),
    )


def downgrade() -> None:
    op.drop_table("runner_ssh_credentials")
