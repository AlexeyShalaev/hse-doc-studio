"""model_servers: серверы ИИ-моделей, поставленные из админки (состояние установки в базе)

Revision ID: ms_01_model_servers
Revises: ri_01_runner_ssh_credentials
Create Date: 2026-11-11 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ms_01_model_servers"
down_revision: str | None = "ri_01_runner_ssh_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_servers",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("engine", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=8), nullable=False),
        sa.Column("credential_id", sa.String(length=32), nullable=True),
        sa.Column("host", sa.String(length=255), server_default="", nullable=False),
        sa.Column("container", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("exposure", sa.String(length=16), server_default="internal", nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("provider_id", sa.String(length=36), nullable=True),
        sa.Column("image", sa.String(length=200), nullable=False),
        sa.Column("steps", sa.Text(), server_default="{}", nullable=False),
        sa.Column("percent", sa.Integer(), nullable=True),
        sa.Column("text", sa.String(length=400), server_default="", nullable=False),
        sa.Column("error", sa.String(length=400), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_servers")),
    )


def downgrade() -> None:
    op.drop_table("model_servers")
