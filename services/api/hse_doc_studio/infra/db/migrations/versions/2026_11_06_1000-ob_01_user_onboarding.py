"""user_onboarding: состояние онбординга пользователя; давним пользователям приглашение вместо тура

Revision ID: ob_01_user_onboarding
Revises: dg_01_diagnostics
Create Date: 2026-11-06 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ob_01_user_onboarding"
down_revision: str | None = "dg_01_diagnostics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_onboarding",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scenario_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("step", sa.String(length=64), nullable=True),
        sa.Column("answers", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'suggested', 'in_progress', 'completed', 'skipped')",
            name=op.f("ck_user_onboarding_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_onboarding_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_onboarding")),
    )
    # Кто уже работал до онбординга, получает ненавязчивое приглашение, а не тур поверх работы.
    op.execute("INSERT INTO user_onboarding (user_id, status) SELECT id, 'suggested' FROM users")


def downgrade() -> None:
    op.drop_table("user_onboarding")
