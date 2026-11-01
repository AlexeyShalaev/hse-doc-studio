"""runner_pairings и провайдер ИИ через раннер

Revision ID: pr_02_runner_pairing_relay
Revises: pr_01_personal_runners
Create Date: 2026-10-31 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "pr_02_runner_pairing_relay"
down_revision: str | None = "pr_01_personal_runners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runner_pairings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("device_code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_code", sa.String(length=9), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("host_kind", sa.String(length=16), nullable=False),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("token_id", sa.String(length=64), nullable=True),
        sa.Column("token_secret_enc", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'denied', 'delivered', 'expired')",
            name=op.f("ck_runner_pairings_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runner_pairings")),
        sa.UniqueConstraint("device_code_hash", name=op.f("uq_runner_pairings_device_code_hash")),
        sa.UniqueConstraint("user_code", name=op.f("uq_runner_pairings_user_code")),
    )
    op.create_index("ix_runner_pairings_expires_at", "runner_pairings", ["expires_at"])

    op.add_column("ai_providers", sa.Column("runner_id", sa.String(length=64), nullable=True))
    op.add_column("ai_providers", sa.Column("runner_endpoint", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        op.f("fk_ai_providers_runner_id_runners"), "ai_providers", "runners", ["runner_id"], ["id"], ondelete="CASCADE"
    )
    op.create_check_constraint(
        "ck_ai_providers_runner",
        "ai_providers",
        "(type = 'runner') = (runner_id IS NOT NULL AND runner_endpoint IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_ai_providers_runner_owner", "ai_providers", "type <> 'runner' OR owner_kind = 'user'"
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_providers_runner_owner", "ai_providers", type_="check")
    op.drop_constraint("ck_ai_providers_runner", "ai_providers", type_="check")
    op.drop_constraint(op.f("fk_ai_providers_runner_id_runners"), "ai_providers", type_="foreignkey")
    op.drop_column("ai_providers", "runner_endpoint")
    op.drop_column("ai_providers", "runner_id")
    op.drop_index("ix_runner_pairings_expires_at", table_name="runner_pairings")
    op.drop_table("runner_pairings")
