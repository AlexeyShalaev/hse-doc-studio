"""projects, project_members

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
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=True),
        sa.Column("owner_org_id", sa.String(length=64), nullable=True),
        sa.Column("workspace_path", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("lang", sa.String(length=8), nullable=False),
        sa.Column("org_visible", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("nda", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("volume_missing_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name=op.f("fk_projects_owner_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index("ix_projects_owner_user_id", "projects", ["owner_user_id"], unique=False)
    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("principal_kind", sa.String(length=16), nullable=False),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("persona", sa.String(length=64), nullable=True),
        sa.Column("can_share", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("show_sources", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("can_edit_all", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_project_members_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", "principal_kind", "principal_id", name=op.f("pk_project_members")),
    )
    op.create_index("ix_project_members_principal", "project_members", ["principal_kind", "principal_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_project_members_principal", table_name="project_members")
    op.drop_table("project_members")
    op.drop_index("ix_projects_owner_user_id", table_name="projects")
    op.drop_table("projects")
