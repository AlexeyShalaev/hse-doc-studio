"""links: ссылки доступа, гостевые сессии, ссылочные права и переходы по ссылкам

Revision ID: cf_01_links
Revises: pr_03_runner_paused_by
Create Date: 2026-11-01 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cf_01_links"
down_revision: str | None = "pr_03_runner_paused_by"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "share_links",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("show_sources", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("require_login", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_enc", sa.Text(), nullable=False),
        sa.Column("token_prefix", sa.String(length=12), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.String(length=64), nullable=True),
        sa.Column("revoke_reason", sa.String(length=16), nullable=True),
        sa.Column("replaced_by", sa.String(length=64), nullable=True),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("role IN ('reader', 'reviewer', 'editor')", name=op.f("ck_share_links_role")),
        sa.CheckConstraint("(revoked_at IS NULL) = (revoke_reason IS NULL)", name=op.f("ck_share_links_revoke")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_share_links_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_share_links_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_share_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_share_links_token_hash")),
    )
    op.create_index(
        "ix_share_links_project_active",
        "share_links",
        ["project_id"],
        unique=False,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("ix_share_links_created_by", "share_links", ["created_by"], unique=False)

    op.create_table(
        "guest_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), server_default="", nullable=False),
        sa.Column("csrf_token", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guest_sessions")),
        sa.UniqueConstraint("secret_hash", name=op.f("uq_guest_sessions_secret_hash")),
    )
    op.create_index("ix_guest_sessions_expires_at", "guest_sessions", ["expires_at"], unique=False)

    op.create_table(
        "guest_session_links",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("link_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["link_id"], ["share_links.id"], name=op.f("fk_guest_session_links_link_id_share_links"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["guest_sessions.id"],
            name=op.f("fk_guest_session_links_session_id_guest_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id", "link_id", name=op.f("pk_guest_session_links")),
    )
    op.create_index("ux_guest_session_links_project", "guest_session_links", ["session_id", "project_id"], unique=True)

    op.create_table(
        "share_link_grants",
        sa.Column("link_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["link_id"], ["share_links.id"], name=op.f("fk_share_link_grants_link_id_share_links"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_share_link_grants_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("link_id", "user_id", name=op.f("pk_share_link_grants")),
    )
    op.create_index("ix_share_link_grants_user_project", "share_link_grants", ["user_id", "project_id"], unique=False)

    op.create_table(
        "share_link_visits",
        sa.Column("link_id", sa.String(length=64), nullable=False),
        sa.Column("visitor_kind", sa.String(length=8), nullable=False),
        sa.Column("visitor_id", sa.String(length=64), nullable=False),
        sa.Column("visitor_name", sa.String(length=128), nullable=True),
        sa.Column("first_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opens", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_ip", sa.String(length=64), nullable=True),
        sa.CheckConstraint("visitor_kind IN ('guest', 'user')", name=op.f("ck_share_link_visits_visitor_kind")),
        sa.ForeignKeyConstraint(
            ["link_id"], ["share_links.id"], name=op.f("fk_share_link_visits_link_id_share_links"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("link_id", "visitor_kind", "visitor_id", name=op.f("pk_share_link_visits")),
    )
    op.create_index(
        "ix_share_link_visits_link_last", "share_link_visits", ["link_id", sa.text("last_at DESC")], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_share_link_visits_link_last", table_name="share_link_visits")
    op.drop_table("share_link_visits")
    op.drop_index("ix_share_link_grants_user_project", table_name="share_link_grants")
    op.drop_table("share_link_grants")
    op.drop_index("ux_guest_session_links_project", table_name="guest_session_links")
    op.drop_table("guest_session_links")
    op.drop_index("ix_guest_sessions_expires_at", table_name="guest_sessions")
    op.drop_table("guest_sessions")
    op.drop_index("ix_share_links_created_by", table_name="share_links")
    op.drop_index("ix_share_links_project_active", table_name="share_links")
    op.drop_table("share_links")
