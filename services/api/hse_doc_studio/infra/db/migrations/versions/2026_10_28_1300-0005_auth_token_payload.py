"""auth_tokens: полезная нагрузка токена (новый адрес при смене e-mail)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-28 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("auth_tokens", sa.Column("payload", sa.String(length=320), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_tokens", "payload")
