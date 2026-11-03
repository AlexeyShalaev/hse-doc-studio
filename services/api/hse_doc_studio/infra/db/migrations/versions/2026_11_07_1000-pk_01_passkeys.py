"""passkeys: ключи входа WebAuthn и отметка повторного подтверждения личности в сессии

Revision ID: pk_01_passkeys
Revises: ob_01_user_onboarding
Create Date: 2026-11-07 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "pk_01_passkeys"
down_revision: str | None = "ob_01_user_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "passkeys",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("credential_id", sa.Text(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rp_id", sa.String(length=253), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("transports", postgresql.ARRAY(sa.String(length=32)), server_default="{}", nullable=False),
        sa.Column("aaguid", sa.String(length=36), server_default="", nullable=False),
        sa.Column("backup_eligible", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("backed_up", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_passkeys_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passkeys")),
        sa.UniqueConstraint("credential_id", name=op.f("uq_passkeys_credential_id")),
    )
    op.create_index("ix_passkeys_user_id", "passkeys", ["user_id"], unique=False)
    op.add_column("sessions", sa.Column("reauth_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "reauth_at")
    op.drop_index("ix_passkeys_user_id", table_name="passkeys")
    op.drop_table("passkeys")
