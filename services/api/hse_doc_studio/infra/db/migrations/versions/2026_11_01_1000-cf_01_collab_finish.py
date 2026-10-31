"""Совместная работа, завершение: приглашения, запросы доступа, передачи владения, уведомления

Ревизия общая на три трека (S22 спецификации collab_finish). На ветке трека invites в ней лежат только
таблицы этого трека (разделы 3.5–3.8); таблицы ссылок и git-remote добавляются в эту же ревизию при слиянии.

Revision ID: cf_01_collab_finish
Revises: pr_03_runner_paused_by
Create Date: 2026-11-01 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "cf_01_collab_finish"
down_revision: str | None = "pr_03_runner_paused_by"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOTIFICATION_KINDS = (
    "project_invitation",
    "invitation_accepted",
    "invitation_declined",
    "access_request",
    "access_request_decided",
    "transfer_request",
    "transfer_decided",
    "member_removed",
)


def _project_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["project_id"], ["projects.id"], name=op.f(f"fk_{table}_project_id_projects"), ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "project_invitations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("invitee_user_id", sa.String(length=64), nullable=True),
        sa.Column("invitee_email", sa.String(length=320), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("persona", sa.String(length=64), nullable=True),
        sa.Column("can_share", sa.Boolean(), nullable=False),
        sa.Column("show_sources", sa.Boolean(), nullable=False),
        sa.Column("can_edit_all", sa.Boolean(), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("invited_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registration_invite_id", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "invitee_user_id IS NOT NULL OR invitee_email IS NOT NULL", name=op.f("ck_project_invitations_invitee")
        ),
        sa.CheckConstraint("role IN ('reader', 'reviewer', 'editor')", name=op.f("ck_project_invitations_role")),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'revoked')", name=op.f("ck_project_invitations_status")
        ),
        _project_fk("project_invitations"),
        sa.ForeignKeyConstraint(
            ["invitee_user_id"],
            ["users.id"],
            name=op.f("fk_project_invitations_invitee_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"], ["users.id"], name=op.f("fk_project_invitations_invited_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_invitations")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_project_invitations_token_hash")),
    )
    op.create_index(
        "ux_project_invitations_pending_user",
        "project_invitations",
        ["project_id", "invitee_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND invitee_user_id IS NOT NULL"),
    )
    op.create_index(
        "ux_project_invitations_pending_email",
        "project_invitations",
        ["project_id", "invitee_email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND invitee_email IS NOT NULL"),
    )
    op.create_index(
        "ix_project_invitations_email_pending",
        "project_invitations",
        ["invitee_email"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_project_invitations_project_created", "project_invitations", ["project_id", sa.text("created_at DESC")]
    )
    op.create_index("ix_project_invitations_invitee_user_id", "project_invitations", ["invitee_user_id"])

    op.create_table(
        "access_requests",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=64), nullable=True),
        sa.Column("granted_role", sa.String(length=16), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'denied', 'cancelled')", name=op.f("ck_access_requests_status")
        ),
        sa.CheckConstraint(
            "(status = 'approved') = (granted_role IS NOT NULL)", name=op.f("ck_access_requests_granted")
        ),
        _project_fk("access_requests"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_access_requests_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_requests")),
    )
    op.create_index(
        "ux_access_requests_pending",
        "access_requests",
        ["project_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_access_requests_user_created", "access_requests", ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_access_requests_project_created", "access_requests", ["project_id", sa.text("created_at DESC")])

    op.create_table(
        "project_transfers",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("from_kind", sa.String(length=8), nullable=False),
        sa.Column("from_id", sa.String(length=64), nullable=False),
        sa.Column("to_kind", sa.String(length=8), nullable=False),
        sa.Column("to_id", sa.String(length=64), nullable=False),
        sa.Column("initiated_by", sa.String(length=64), nullable=True),
        sa.Column("message", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled', 'superseded')",
            name=op.f("ck_project_transfers_status"),
        ),
        sa.CheckConstraint(
            "from_kind IN ('user', 'org') AND to_kind IN ('user', 'org')", name=op.f("ck_project_transfers_kinds")
        ),
        _project_fk("project_transfers"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_transfers")),
    )
    op.create_index(
        "ux_project_transfers_pending",
        "project_transfers",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_project_transfers_to_pending",
        "project_transfers",
        ["to_kind", "to_id"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=128), nullable=True),
        sa.CheckConstraint(f"kind IN {_NOTIFICATION_KINDS!r}", name=op.f("ck_notifications_kind")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", sa.text("created_at DESC")])
    op.create_index(
        "ix_notifications_user_unread", "notifications", ["user_id"], postgresql_where=sa.text("read_at IS NULL")
    )
    op.create_index(
        "ux_notifications_dedupe",
        "notifications",
        ["user_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ux_notifications_dedupe", table_name="notifications")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_project_transfers_to_pending", table_name="project_transfers")
    op.drop_index("ux_project_transfers_pending", table_name="project_transfers")
    op.drop_table("project_transfers")
    op.drop_index("ix_access_requests_project_created", table_name="access_requests")
    op.drop_index("ix_access_requests_user_created", table_name="access_requests")
    op.drop_index("ux_access_requests_pending", table_name="access_requests")
    op.drop_table("access_requests")
    op.drop_index("ix_project_invitations_invitee_user_id", table_name="project_invitations")
    op.drop_index("ix_project_invitations_project_created", table_name="project_invitations")
    op.drop_index("ix_project_invitations_email_pending", table_name="project_invitations")
    op.drop_index("ux_project_invitations_pending_email", table_name="project_invitations")
    op.drop_index("ux_project_invitations_pending_user", table_name="project_invitations")
    op.drop_table("project_invitations")
