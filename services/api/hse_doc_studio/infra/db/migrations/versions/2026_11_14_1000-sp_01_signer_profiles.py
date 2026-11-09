"""signer_profiles: профиль подписанта, картинка подписи и открытая часть ключа для плашки

Revision ID: sp_01_signer_profiles
Revises: jb_01_jobs_batch_id
Create Date: 2026-11-14 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "sp_01_signer_profiles"
down_revision: str | None = "jb_01_jobs_batch_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signer_profiles",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("image_png", sa.LargeBinary(), nullable=True),
        sa.Column("image_sha256", sa.String(length=64), nullable=True),
        sa.Column("image_width_px", sa.Integer(), nullable=True),
        sa.Column("image_height_px", sa.Integer(), nullable=True),
        sa.Column("image_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("key_kind", sa.String(length=16), nullable=True),
        sa.Column("key_data", sa.LargeBinary(), nullable=True),
        sa.Column("key_plate", postgresql.JSONB(), nullable=True),
        sa.Column("key_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("key_kind IN ('x509', 'openpgp')", name=op.f("ck_signer_profiles_key_kind")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_signer_profiles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_signer_profiles")),
    )


def downgrade() -> None:
    op.drop_table("signer_profiles")
