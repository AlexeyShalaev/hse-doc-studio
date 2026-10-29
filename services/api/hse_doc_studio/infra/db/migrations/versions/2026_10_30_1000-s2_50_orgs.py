"""orgs, org_members, groups, group_members: организации и группы; projects.owner_org_id получает внешний ключ

Revision ID: s2_50_orgs
Revises: s2_73_runners
Create Date: 2026-10-30 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s2_50_orgs"
down_revision: str | None = "s2_73_runners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "policies", postgresql.JSONB(), server_default=sa.text("""'{"version": 1}'::jsonb"""), nullable=False
        ),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_orgs_created_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orgs")),
        sa.UniqueConstraint("slug", name=op.f("uq_orgs_slug")),
    )
    op.create_table(
        "org_members",
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('member', 'admin', 'owner')", name=op.f("ck_org_members_org_member_role")),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], name=op.f("fk_org_members_org_id_orgs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_org_members_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("org_id", "user_id", name=op.f("pk_org_members")),
    )
    op.create_index("ix_org_members_user_id", "org_members", ["user_id"], unique=False)
    op.create_table(
        "groups",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("external_ref", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"], name=op.f("fk_groups_org_id_orgs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_groups")),
    )
    op.create_index("ux_groups_org_name_lower", "groups", ["org_id", sa.text("lower(name)")], unique=True)
    op.create_table(
        "group_members",
        sa.Column("group_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["groups.id"], name=op.f("fk_group_members_group_id_groups"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_group_members_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("group_id", "user_id", name=op.f("pk_group_members")),
    )
    op.create_index("ix_group_members_user_id", "group_members", ["user_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_projects_owner_org_id_orgs"), "projects", "orgs", ["owner_org_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("ix_projects_owner_org_id", "projects", ["owner_org_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_projects_owner_org_id", table_name="projects")
    op.drop_constraint(op.f("fk_projects_owner_org_id_orgs"), "projects", type_="foreignkey")
    op.drop_index("ix_group_members_user_id", table_name="group_members")
    op.drop_table("group_members")
    op.drop_index("ux_groups_org_name_lower", table_name="groups")
    op.drop_table("groups")
    op.drop_index("ix_org_members_user_id", table_name="org_members")
    op.drop_table("org_members")
    op.drop_table("orgs")
