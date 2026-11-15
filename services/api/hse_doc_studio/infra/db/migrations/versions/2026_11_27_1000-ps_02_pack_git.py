"""pack_studio_service_access и колонки git рабочего пространства: служебный доступ, форк, отправленная вершина (T6)

Только дописывание: новая таблица и колонки с NULL. Старая версия api их не читает и не пишет (правило expand/contract,
docs/ru/deploy/operations.md); её запись строки пространства новые колонки не трогает.

Revision ID: ps_02_pack_git
Revises: ps_01_pack_workspaces
Create Date: 2026-11-27 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ps_02_pack_git"
down_revision: str | None = "ps_01_pack_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pack_studio_service_access",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("repo_key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("token_family", sa.String(length=32), nullable=True),
        sa.Column("secret_enc", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repo_key", name=op.f("uq_pack_studio_service_access_repo_key")),
    )
    op.add_column("pack_workspaces", sa.Column("service_access_id", sa.Uuid(), nullable=True))
    op.add_column("pack_workspaces", sa.Column("fork_url", sa.Text(), nullable=True))
    op.add_column("pack_workspaces", sa.Column("pushed_sha", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        op.f("fk_pack_workspaces_service_access_id_pack_studio_service_access"),
        "pack_workspaces",
        "pack_studio_service_access",
        ["service_access_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_pack_workspaces_service_access_id_pack_studio_service_access"), "pack_workspaces", type_="foreignkey"
    )
    op.drop_column("pack_workspaces", "pushed_sha")
    op.drop_column("pack_workspaces", "fork_url")
    op.drop_column("pack_workspaces", "service_access_id")
    op.drop_table("pack_studio_service_access")
