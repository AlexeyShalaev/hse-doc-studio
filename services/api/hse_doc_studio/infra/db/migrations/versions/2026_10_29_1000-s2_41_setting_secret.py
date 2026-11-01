"""instance_settings.secret_enc: шифртекст секретной настройки (пароль SMTP)

Revision ID: s2_41_setting_secret
Revises: s2_44_audit_purge
Create Date: 2026-10-29 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "s2_41_setting_secret"
down_revision: str | None = "s2_44_audit_purge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("instance_settings", sa.Column("secret_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("instance_settings", "secret_enc")
