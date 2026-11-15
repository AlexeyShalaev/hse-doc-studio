"""Официальные паки (T22): доступ бота в режиме форка и согласие с лицензией в рабочем пространстве

Только дописывание: колонки с NULL или значением по умолчанию. Старая версия api их не читает и не пишет (правило
expand/contract, docs/ru/deploy/operations.md); прежние служебные доступы остаются прямыми (`fork_mode` false).

Revision ID: ps_03_pack_official
Revises: ps_02_pack_git
Create Date: 2026-11-28 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ps_03_pack_official"
down_revision: str | None = "ps_02_pack_git"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pack_studio_service_access",
        sa.Column("fork_mode", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("pack_studio_service_access", sa.Column("fork_url", sa.Text(), nullable=True))
    op.add_column("pack_workspaces", sa.Column("license_accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("pack_workspaces", "license_accepted_at")
    op.drop_column("pack_studio_service_access", "fork_url")
    op.drop_column("pack_studio_service_access", "fork_mode")
