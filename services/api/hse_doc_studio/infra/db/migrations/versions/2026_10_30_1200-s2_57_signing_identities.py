"""signing_identities: идентичности подписи пользователей, закрытый ключ шифртекстом

Revision ID: s2_57_signing_identities
Revises: s2_56_ai_providers
Create Date: 2026-10-30 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s2_57_signing_identities"
down_revision: str | None = "s2_56_ai_providers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signing_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("subject_cn", sa.Text(), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trusted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=True),
        sa.Column("protected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("cert_pem", sa.Text(), nullable=True),
        sa.Column("key_enc", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signing_identities_owner", "signing_identities", ["owner_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_signing_identities_owner", table_name="signing_identities")
    op.drop_table("signing_identities")
