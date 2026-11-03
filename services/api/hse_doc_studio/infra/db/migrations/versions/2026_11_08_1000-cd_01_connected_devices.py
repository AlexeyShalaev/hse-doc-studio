"""подключённые Студии: сигнал присутствия устройства; коммит и отпечаток PDF в записи сборки

Revision ID: cd_01_connected_devices
Revises: pk_01_passkeys
Create Date: 2026-11-08 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "cd_01_connected_devices"
down_revision: str | None = "pk_01_passkeys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connected_devices",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("os", sa.String(length=16), nullable=False),
        sa.Column("activity", sa.String(length=16), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_id", sa.String(length=64), nullable=True),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("project_ids", postgresql.ARRAY(sa.String(length=36)), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_connected_devices_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "device_id", name=op.f("pk_connected_devices")),
    )
    op.create_index("ix_connected_devices_last_seen", "connected_devices", ["last_seen_at"], unique=False)
    op.create_index(
        "ix_connected_devices_project_ids", "connected_devices", ["project_ids"], unique=False, postgresql_using="gin"
    )
    op.add_column("compile_records", sa.Column("source_commit", sa.String(length=64), nullable=True))
    op.add_column("compile_records", sa.Column("output_sha256", sa.String(length=64), nullable=True))
    op.add_column("compile_records", sa.Column("output_size", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("compile_records", "output_size")
    op.drop_column("compile_records", "output_sha256")
    op.drop_column("compile_records", "source_commit")
    op.drop_index("ix_connected_devices_project_ids", table_name="connected_devices", postgresql_using="gin")
    op.drop_index("ix_connected_devices_last_seen", table_name="connected_devices")
    op.drop_table("connected_devices")
