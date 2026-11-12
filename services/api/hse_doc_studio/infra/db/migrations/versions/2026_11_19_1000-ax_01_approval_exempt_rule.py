"""users.approval_exempt_rule: правило исключения из одобрения, по которому аккаунт ждёт только подтверждения почты

Expand: новая колонка с пустым значением, прежний код её не читает и не пишет.

Revision ID: ax_01_approval_exempt_rule
Revises: ml_03_drop_mail_outbox
Create Date: 2026-11-19 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ax_01_approval_exempt_rule"
down_revision: str | None = "ml_03_drop_mail_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("approval_exempt_rule", sa.String(length=320), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "approval_exempt_rule")
