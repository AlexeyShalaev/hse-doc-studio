"""runners.paused_by: кто поставил раннер на паузу

Revision ID: pr_03_runner_paused_by
Revises: pr_02_runner_pairing_relay
Create Date: 2026-10-31 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "pr_03_runner_paused_by"
down_revision: str | None = "pr_02_runner_pairing_relay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runners", sa.Column("paused_by", sa.String(length=16), nullable=True))
    # Общие раннеры ставил на паузу только админ; кто ставил личные, неизвестно, считаем хозяина (мягче).
    op.execute(
        "UPDATE runners SET paused_by = CASE WHEN owner_kind = 'instance' THEN 'admin' ELSE 'owner' END WHERE paused"
    )
    op.create_check_constraint(
        op.f("ck_runners_paused_by"), "runners", "paused_by IS NULL OR paused_by IN ('owner', 'admin')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_runners_paused_by"), "runners", type_="check")
    op.drop_column("runners", "paused_by")
