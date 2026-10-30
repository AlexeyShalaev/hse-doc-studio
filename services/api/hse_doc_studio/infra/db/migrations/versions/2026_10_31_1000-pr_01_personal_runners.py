"""personal runners: владелец-человек у раннеров, маршрут задач, политика сборок проекта

Revision ID: pr_01_personal_runners
Revises: s2_68_project_usage
Create Date: 2026-10-31 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "pr_01_personal_runners"
down_revision: str | None = "s2_68_project_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OWNER = "(owner_kind = 'instance' AND owner_id IS NULL) OR (owner_kind = 'user' AND owner_id IS NOT NULL)"


def upgrade() -> None:
    op.add_column("runners", sa.Column("host_kind", sa.String(length=16), server_default="cli", nullable=False))
    op.add_column(
        "runners",
        sa.Column("features", postgresql.ARRAY(sa.String(length=32)), server_default="{}", nullable=False),
    )
    op.add_column("runners", sa.Column("ai_endpoints", postgresql.JSONB(), server_default="[]", nullable=False))
    op.add_column("runners", sa.Column("ai_concurrency", sa.Integer(), server_default="0", nullable=False))
    op.add_column("runners", sa.Column("last_seen_ip", sa.String(length=64), nullable=True))
    op.add_column("runners", sa.Column("offline_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("runners", sa.Column("renamed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(op.f("ck_runners_owner"), "runners", _OWNER)
    op.create_check_constraint(op.f("ck_runners_ai_concurrency"), "runners", "ai_concurrency >= 0")

    op.add_column(
        "runner_registration_tokens",
        sa.Column("purpose", sa.String(length=16), server_default="manual", nullable=False),
    )
    op.create_check_constraint(op.f("ck_runner_registration_tokens_owner"), "runner_registration_tokens", _OWNER)

    op.add_column("projects", sa.Column("build_runners", sa.String(length=16), server_default="shared", nullable=False))
    op.create_check_constraint(op.f("ck_projects_build_runners"), "projects", "build_runners IN ('shared', 'owner')")

    op.add_column("jobs", sa.Column("route", sa.String(length=16), server_default="shared", nullable=False))
    op.add_column("jobs", sa.Column("route_owner_id", sa.String(length=64), nullable=True))
    op.add_column("jobs", sa.Column("personal_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("target_runner_id", sa.Uuid(), nullable=True))
    op.add_column("jobs", sa.Column("runner_scope", sa.String(length=16), nullable=True))
    op.add_column("jobs", sa.Column("route_reason", sa.String(length=32), nullable=True))
    op.add_column("jobs", sa.Column("vcost", sa.Double(), server_default="1.0", nullable=False))
    op.add_column("jobs", sa.Column("timeout_personal_s", sa.Double(), nullable=True))
    op.create_check_constraint(op.f("ck_jobs_route"), "jobs", "route IN ('shared', 'personal_first', 'pinned')")
    op.create_check_constraint(
        op.f("ck_jobs_route_pinned"), "jobs", "(route = 'pinned') = (target_runner_id IS NOT NULL)"
    )
    op.create_check_constraint(
        op.f("ck_jobs_route_personal"),
        "jobs",
        "(route = 'personal_first') = (route_owner_id IS NOT NULL AND personal_until IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_jobs_runner_scope"), "jobs", "runner_scope IS NULL OR runner_scope IN ('shared', 'personal')"
    )
    op.create_index(
        "ix_jobs_queued_personal",
        "jobs",
        ["route_owner_id", "priority_class", "vtime", "queued_at", "seq"],
        postgresql_where=sa.text("state = 'queued' AND route = 'personal_first'"),
    )
    op.create_index(
        "ix_jobs_queued_pinned",
        "jobs",
        ["target_runner_id"],
        postgresql_where=sa.text("state = 'queued' AND route = 'pinned'"),
    )
    op.create_index(
        "ix_jobs_running_shared_user",
        "jobs",
        ["user_id"],
        postgresql_where=sa.text("state = 'running' AND runner_scope = 'shared'"),
    )
    op.create_index(
        "ix_jobs_running_shared_org",
        "jobs",
        ["org_id"],
        postgresql_where=sa.text("state = 'running' AND runner_scope = 'shared'"),
    )
    # До этого этапа задачи брали только общие раннеры.
    op.execute("UPDATE jobs SET runner_scope = 'shared' WHERE runner_id IS NOT NULL")


def downgrade() -> None:
    op.drop_index("ix_jobs_running_shared_org", table_name="jobs")
    op.drop_index("ix_jobs_running_shared_user", table_name="jobs")
    op.drop_index("ix_jobs_queued_pinned", table_name="jobs")
    op.drop_index("ix_jobs_queued_personal", table_name="jobs")
    for name in ("ck_jobs_runner_scope", "ck_jobs_route_personal", "ck_jobs_route_pinned", "ck_jobs_route"):
        op.drop_constraint(op.f(name), "jobs", type_="check")
    for column in (
        "timeout_personal_s",
        "vcost",
        "route_reason",
        "runner_scope",
        "target_runner_id",
        "personal_until",
        "route_owner_id",
        "route",
    ):
        op.drop_column("jobs", column)
    op.drop_constraint(op.f("ck_projects_build_runners"), "projects", type_="check")
    op.drop_column("projects", "build_runners")
    op.drop_constraint(op.f("ck_runner_registration_tokens_owner"), "runner_registration_tokens", type_="check")
    op.drop_column("runner_registration_tokens", "purpose")
    op.drop_constraint(op.f("ck_runners_ai_concurrency"), "runners", type_="check")
    op.drop_constraint(op.f("ck_runners_owner"), "runners", type_="check")
    for column in (
        "renamed_at",
        "offline_at",
        "last_seen_ip",
        "ai_concurrency",
        "ai_endpoints",
        "features",
        "host_kind",
    ):
        op.drop_column("runners", column)
