"""Ревью-комментарии: треды и комментарии, новые виды уведомлений

Revision ID: s5_01_review
Revises: s6_01_quotas_gateway
Create Date: 2026-11-03 10:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s5_01_review"
down_revision: str | None = "s6_01_quotas_gateway"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_KINDS = (
    "project_invitation",
    "invitation_accepted",
    "invitation_declined",
    "access_request",
    "access_request_decided",
    "transfer_request",
    "transfer_decided",
    "member_removed",
)
_NEW_KINDS = (*_OLD_KINDS, "review_thread", "review_reply", "review_mention", "review_resolved")


def _replace_kind_check(kinds: tuple[str, ...]) -> None:
    op.drop_constraint(op.f("ck_notifications_kind"), "notifications", type_="check")
    op.create_check_constraint(op.f("ck_notifications_kind"), "notifications", f"kind IN {kinds!r}")


def upgrade() -> None:
    op.create_table(
        "review_threads",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("anchor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_by_name", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_by", sa.String(length=64), nullable=True),
        sa.Column("resolved_by_name", sa.String(length=256), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open', 'resolved')", name=op.f("ck_review_threads_status")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_review_threads_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_threads")),
    )
    op.create_index("ix_review_threads_project_path", "review_threads", ["project_id", "path"])
    op.create_index("ix_review_threads_project_activity", "review_threads", ["project_id", sa.text("updated_at DESC")])
    op.create_table(
        "review_comments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("author_id", sa.String(length=64), nullable=True),
        sa.Column("author_name", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("mentions", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["thread_id"], ["review_threads.id"], name=op.f("fk_review_comments_thread_id_review_threads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_comments")),
    )  # fmt: skip
    op.create_index("ix_review_comments_thread_created", "review_comments", ["thread_id", "created_at"])
    _replace_kind_check(_NEW_KINDS)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind LIKE 'review\\_%'")
    _replace_kind_check(_OLD_KINDS)
    op.drop_index("ix_review_comments_thread_created", table_name="review_comments")
    op.drop_table("review_comments")
    op.drop_index("ix_review_threads_project_activity", table_name="review_threads")
    op.drop_index("ix_review_threads_project_path", table_name="review_threads")
    op.drop_table("review_threads")
