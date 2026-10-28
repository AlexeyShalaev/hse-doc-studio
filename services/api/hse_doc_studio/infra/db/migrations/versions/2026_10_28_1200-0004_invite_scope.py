"""registration_invites: публичный id, организация и роль приглашения

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("registration_invites", sa.Column("id", sa.String(length=64), nullable=True))
    # Уже выданные приглашения получают id из начала хеша: тот же способ берёт хранилище для записей без id.
    op.execute("UPDATE registration_invites SET id = substr(token_hash, 1, 32) WHERE id IS NULL")
    op.alter_column("registration_invites", "id", nullable=False)
    op.create_unique_constraint(op.f("uq_registration_invites_id"), "registration_invites", ["id"])
    op.add_column("registration_invites", sa.Column("org_id", sa.String(length=64), nullable=True))
    op.add_column("registration_invites", sa.Column("org_role", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("registration_invites", "org_role")
    op.drop_column("registration_invites", "org_id")
    op.drop_constraint(op.f("uq_registration_invites_id"), "registration_invites", type_="unique")
    op.drop_column("registration_invites", "id")
