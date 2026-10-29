"""ai_providers: ИИ-провайдеры пользователей и общие провайдеры установки, ключ шифртекстом

Revision ID: s2_56_ai_providers
Revises: s2_59_chats
Create Date: 2026-10-30 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "s2_56_ai_providers"
down_revision: str | None = "s2_59_chats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_providers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_kind", sa.String(length=16), server_default="user", nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("api_key_enc", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), server_default="", nullable=False),
        sa.Column("models", JSONB(), server_default="[]", nullable=False),
        sa.Column("ssl_verify", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("connect_timeout_s", sa.Float(), server_default="10", nullable=False),
        sa.Column("request_timeout_s", sa.Float(), server_default="60", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(owner_kind = 'user' AND owner_id IS NOT NULL) OR (owner_kind = 'instance' AND owner_id IS NULL)",
            name="ck_ai_providers_owner",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_providers_owner", "ai_providers", ["owner_kind", "owner_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_providers_owner", table_name="ai_providers")
    op.drop_table("ai_providers")
