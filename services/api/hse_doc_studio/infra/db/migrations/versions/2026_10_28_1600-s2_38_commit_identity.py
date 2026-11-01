"""users.commit_*: подпись коммитов человека (свои имя и адрес, согласие на e-mail аккаунта)

Revision ID: s2_38_commit_identity
Revises: s2_41_setting_secret
Create Date: 2026-10-28 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s2_38_commit_identity"
down_revision: str | None = "s2_41_setting_secret"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("commit_name", sa.String(length=256), nullable=True))
    op.add_column("users", sa.Column("commit_email", sa.String(length=320), nullable=True))
    op.add_column("users", sa.Column("commit_use_account_email", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "commit_use_account_email")
    op.drop_column("users", "commit_email")
    op.drop_column("users", "commit_name")
