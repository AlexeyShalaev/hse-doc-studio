"""device_authorizations и происхождение токенов доступа (сервер как git-remote)

Часть общей ревизии `cf_01_collab_finish` (S22), которую кладёт трек gitremote: таблица входа устройства
по коду и колонки `api_tokens.origin`, `client_name`, `client_kind`. При слиянии треков ставится в цепочку
за общей ревизией (правка `down_revision`) или вливается в неё.

Revision ID: cf_01g_git_remote
Revises: pr_03_runner_paused_by
Create Date: 2026-11-01 10:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "cf_01g_git_remote"
down_revision: str | None = "pr_03_runner_paused_by"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_authorizations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("device_code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_code", sa.String(length=9), nullable=False),
        sa.Column("client_name", sa.String(length=128), nullable=False),
        sa.Column("client_kind", sa.String(length=16), nullable=False),
        sa.Column("requested_scopes", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("granted_scopes", postgresql.ARRAY(sa.String(length=32)), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("token_id", sa.String(length=64), nullable=True),
        sa.Column("token_secret_enc", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'denied', 'delivered')",
            name=op.f("ck_device_authorizations_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_authorizations")),
        sa.UniqueConstraint("device_code_hash", name=op.f("uq_device_authorizations_device_code_hash")),
        sa.UniqueConstraint("user_code", name=op.f("uq_device_authorizations_user_code")),
    )
    op.create_index("ix_device_authorizations_expires_at", "device_authorizations", ["expires_at"])

    op.add_column("api_tokens", sa.Column("origin", sa.String(length=16), server_default="manual", nullable=False))
    op.add_column("api_tokens", sa.Column("client_name", sa.String(length=128), nullable=True))
    op.add_column("api_tokens", sa.Column("client_kind", sa.String(length=16), nullable=True))
    op.create_check_constraint(op.f("ck_api_tokens_origin"), "api_tokens", "origin IN ('manual', 'device')")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_api_tokens_origin"), "api_tokens", type_="check")
    op.drop_column("api_tokens", "client_kind")
    op.drop_column("api_tokens", "client_name")
    op.drop_column("api_tokens", "origin")
    op.drop_index("ix_device_authorizations_expires_at", table_name="device_authorizations")
    op.drop_table("device_authorizations")
