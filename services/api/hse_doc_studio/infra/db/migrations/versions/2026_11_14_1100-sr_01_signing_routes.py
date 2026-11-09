"""Маршруты подписания: маршрут, документы, участники и события (docs/design/signing-route.md, раздел 5.8)

Revision ID: sr_01_signing_routes
Revises: sp_01_signer_profiles
Create Date: 2026-11-14 11:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "sr_01_signing_routes"
down_revision: str | None = "sp_01_signer_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = ("draft", "active", "paused", "returned", "completed", "cancelled", "archived")
_PHASES = ("approval", "signing", "done")
_STOP_REASONS = ("rebuilt", "frozen_changed", "marks_changed", "participant_left", "returned")
_OPEN = sa.text("status IN ('draft', 'active', 'paused', 'returned')")
_WATCHING = sa.text("status IN ('active', 'completed')")
_JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # Новые таблицы: прежняя версия api их не знает и не трогает.
    op.create_table(
        "signing_routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=True),
        sa.Column("round", sa.Integer(), server_default="0", nullable=False),
        sa.Column("snapshot", _JSONB, server_default="[]", nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("stop_reason", sa.String(length=32), nullable=True),
        sa.Column("stopped_by", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("sent_by", sa.String(length=64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"status IN {_STATUSES!r}", name=op.f("ck_signing_routes_status")),
        sa.CheckConstraint(f"phase IS NULL OR phase IN {_PHASES!r}", name=op.f("ck_signing_routes_phase")),
        sa.CheckConstraint(
            f"stop_reason IS NULL OR stop_reason IN {_STOP_REASONS!r}", name=op.f("ck_signing_routes_stop_reason")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_signing_routes_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signing_routes")),
    )
    op.create_index(
        "ix_signing_routes_project_profile", "signing_routes", ["project_id", "profile_id", sa.text("created_at DESC")]
    )
    op.create_index("ix_signing_routes_watching", "signing_routes", ["project_id"], postgresql_where=_WATCHING)
    op.create_index(
        "ux_signing_routes_open", "signing_routes", ["project_id", "profile_id"], unique=True, postgresql_where=_OPEN
    )
    op.create_table(
        "signing_route_docs",
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("doc_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["route_id"], ["signing_routes.id"], name=op.f("fk_signing_route_docs_route_id_signing_routes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("route_id", "doc_id", name=op.f("pk_signing_route_docs")),
    )  # fmt: skip
    op.create_index(
        "ux_signing_route_docs_active",
        "signing_route_docs",
        ["project_id", "doc_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_table(
        "signing_route_participants",
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("persona", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("invitation_id", sa.String(length=64), nullable=True),
        sa.Column("assignments", _JSONB, server_default="[]", nullable=False),
        sa.Column("approval", _JSONB, nullable=True),
        sa.Column("notified", _JSONB, nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminders", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(
            ["route_id"], ["signing_routes.id"], name=op.f("fk_signing_route_participants_route_id_signing_routes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("route_id", "id", name=op.f("pk_signing_route_participants")),
    )  # fmt: skip
    op.create_index("ix_signing_route_participants_route", "signing_route_participants", ["route_id", "position"])
    op.create_index(
        "ix_signing_route_participants_user",
        "signing_route_participants",
        ["user_id"],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_signing_route_participants_invitation",
        "signing_route_participants",
        ["invitation_id"],
        postgresql_where=sa.text("invitation_id IS NOT NULL"),
    )
    op.create_table(
        "signing_route_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("participant_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("details", _JSONB, server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(
            ["route_id"], ["signing_routes.id"], name=op.f("fk_signing_route_events_route_id_signing_routes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signing_route_events")),
    )  # fmt: skip
    op.create_index("ix_signing_route_events_route", "signing_route_events", ["route_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_signing_route_events_route", table_name="signing_route_events")
    op.drop_table("signing_route_events")
    op.drop_index(
        "ix_signing_route_participants_invitation",
        table_name="signing_route_participants",
        postgresql_where=sa.text("invitation_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_signing_route_participants_user",
        table_name="signing_route_participants",
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.drop_index("ix_signing_route_participants_route", table_name="signing_route_participants")
    op.drop_table("signing_route_participants")
    op.drop_index("ux_signing_route_docs_active", table_name="signing_route_docs", postgresql_where=sa.text("active"))
    op.drop_table("signing_route_docs")
    op.drop_index("ux_signing_routes_open", table_name="signing_routes", postgresql_where=_OPEN)
    op.drop_index("ix_signing_routes_watching", table_name="signing_routes", postgresql_where=_WATCHING)
    op.drop_index("ix_signing_routes_project_profile", table_name="signing_routes")
    op.drop_table("signing_routes")
