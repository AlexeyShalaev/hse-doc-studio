"""pack_workspaces и pack_studio_grants: рабочие пространства Студии шаблонов и право «Автор шаблонов» (T5)

Только новые таблицы: старая версия api их не читает и не пишет (правило expand/contract, docs/ru/deploy/operations.md).
Включение раздела живёт в instance_settings (`pack_studio.enabled`), миграции не требует.

Revision ID: ps_01_pack_workspaces
Revises: dk_03_runner_disk_auto
Create Date: 2026-11-26 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ps_01_pack_workspaces"
down_revision: str | None = "dk_03_runner_disk_auto"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Значения зафиксированы на момент миграции: новые виды и состояния добавит своя миграция.
_KINDS = ("git", "folder")
_STATES = ("cloning", "ready", "failed")


def upgrade() -> None:
    op.create_table(
        "pack_workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("packs_path", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("remote_url", sa.Text(), nullable=True),
        sa.Column("credential_id", sa.Uuid(), nullable=True),
        sa.Column("insecure_http", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("base_branch", sa.Text(), nullable=True),
        sa.Column("base_sha", sa.String(length=64), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("work_branch", sa.Text(), nullable=True),
        sa.Column("pr_url", sa.Text(), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("ci_status", sa.String(length=32), nullable=True),
        sa.Column("folder", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"kind IN {_KINDS!r}", name=op.f("ck_pack_workspaces_kind")),
        sa.CheckConstraint(f"state IN {_STATES!r}", name=op.f("ck_pack_workspaces_state")),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credential_id"], ["git_credentials.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pack_workspaces_owner_created", "pack_workspaces", ["owner_id", "created_at"])
    op.create_table(
        "pack_studio_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("group_id", sa.String(length=64), nullable=True),
        sa.Column("granted_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(user_id IS NULL) <> (group_id IS NULL)", name=op.f("ck_pack_studio_grants_one_subject")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_pack_studio_grants_user",
        "pack_studio_grants",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "ux_pack_studio_grants_group",
        "pack_studio_grants",
        ["group_id"],
        unique=True,
        postgresql_where=sa.text("group_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_pack_studio_grants_group", table_name="pack_studio_grants")
    op.drop_index("ux_pack_studio_grants_user", table_name="pack_studio_grants")
    op.drop_table("pack_studio_grants")
    op.drop_index("ix_pack_workspaces_owner_created", table_name="pack_workspaces")
    op.drop_table("pack_workspaces")
