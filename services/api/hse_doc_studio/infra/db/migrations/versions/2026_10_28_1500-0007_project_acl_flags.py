"""projects.team, projects.shared_enabled: поля проекта, от которых зависят права

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-28 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("team", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("projects", sa.Column("shared_enabled", sa.Boolean(), server_default="true", nullable=False))


def downgrade() -> None:
    op.drop_column("projects", "shared_enabled")
    op.drop_column("projects", "team")
