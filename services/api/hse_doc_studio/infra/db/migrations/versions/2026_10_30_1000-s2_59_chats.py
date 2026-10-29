"""chats: личные чаты агента (сессии, реплики, сводки, ходы)

Revision ID: s2_59_chats
Revises: s2_73_runners
Create Date: 2026-10-30 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "s2_59_chats"
down_revision: str | None = "s2_73_runners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), server_default="", nullable=False),
        sa.Column("doc_id", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("default_provider_id", sa.Uuid(), nullable=True),
        sa.Column("default_model", sa.String(length=256), nullable=True),
        sa.Column("persona", sa.String(length=128), nullable=True),
        sa.Column("persona_instructions", sa.Text(), nullable=True),
        sa.Column("message_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_run_id", sa.Uuid(), nullable=True),
        sa.Column("compacted_through_seq", sa.Integer(), server_default="-1", nullable=False),
        sa.Column("summary_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_context_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_sessions_owner_scope", "chat_sessions", ["owner_id", "is_system", "project_id", "updated_at"]
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("blocks", JSONB(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=True),
        sa.Column("provider_id", sa.Uuid(), nullable=True),
        sa.Column("usage", JSONB(), nullable=True),
        sa.Column("approval", sa.String(length=32), server_default="auto", nullable=False),
        sa.Column("compacted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "seq", name="uq_chat_messages_session_seq"),
    )
    op.create_table(
        "chat_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("covers_from_seq", sa.Integer(), nullable=False),
        sa.Column("covers_to_seq", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("text", sa.Text(), server_default="", nullable=False),
        sa.Column("model", sa.String(length=256), nullable=True),
        sa.Column("token_estimate", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_summaries_session_created", "chat_summaries", ["session_id", "created_at"])
    op.create_table(
        "chat_agent_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column("first_emitted_seq", sa.Integer(), nullable=True),
        sa.Column("last_emitted_seq", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=256), nullable=True),
        sa.Column("provider_id", sa.Uuid(), nullable=True),
        sa.Column("iterations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("usage", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("diagnostics", JSONB(), server_default="[]", nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_agent_runs_session_created", "chat_agent_runs", ["session_id", "created_at"])
    op.create_index(
        "ix_chat_agent_runs_unfinished",
        "chat_agent_runs",
        ["session_id"],
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("ix_chat_agent_runs_unfinished", table_name="chat_agent_runs")
    op.drop_index("ix_chat_agent_runs_session_created", table_name="chat_agent_runs")
    op.drop_table("chat_agent_runs")
    op.drop_index("ix_chat_summaries_session_created", table_name="chat_summaries")
    op.drop_table("chat_summaries")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_owner_scope", table_name="chat_sessions")
    op.drop_table("chat_sessions")
