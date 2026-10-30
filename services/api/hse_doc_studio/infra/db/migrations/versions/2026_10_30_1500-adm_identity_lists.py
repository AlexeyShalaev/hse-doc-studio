"""adm_identity_lists: индексы серверных списков людей, организаций, приглашений, журнала и проектов; копия
закрепления и руководителя проекта в каталоге

Списки админки ищут, фильтруют, сортируют и листают в базе. Индексы под порядок по умолчанию и частые
фильтры; поиск подстроки по людям дополнительно ускоряет pg_trgm, если расширение доступно.

Revision ID: adm_identity_lists
Revises: s2_68_project_usage
Create Date: 2026-10-30 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "adm_identity_lists"
down_revision: str | None = "s2_68_project_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Триграммы (ix_trgm_*) не входят в модели, их может не быть: проверка дрейфа пропускает индексы с этим префиксом.
# Создать расширение может только роль с правами; без них поиск по людям идёт без триграмм.
_TRGM = """
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
    EXCEPTION WHEN insufficient_privilege OR undefined_file OR feature_not_supported THEN
        RAISE NOTICE 'pg_trgm недоступно: поиск по людям без триграммных индексов';
    END;
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        CREATE INDEX IF NOT EXISTS ix_trgm_users_name ON users USING gin (lower(name) gin_trgm_ops);
        CREATE INDEX IF NOT EXISTS ix_trgm_users_email ON users USING gin (email_normalized gin_trgm_ops);
    END IF;
END
$$
"""


def upgrade() -> None:
    op.create_index("ix_users_created_at_id", "users", [sa.text("created_at DESC"), "id"])
    op.create_index("ix_users_name_lower", "users", [sa.text("lower(name)")])
    op.create_index("ix_users_status_created_at", "users", ["status", sa.text("created_at DESC")])
    op.execute(_TRGM)

    op.create_index("ix_orgs_name_lower", "orgs", [sa.text("lower(name)")])
    op.create_index("ix_org_members_org_created", "org_members", ["org_id", "created_at"])
    op.create_index("ix_org_members_org_role", "org_members", ["org_id", "role"])
    op.create_index("ix_group_members_group_created", "group_members", ["group_id", "created_at"])

    op.create_index("ix_registration_invites_expires_id", "registration_invites", [sa.text("expires_at DESC"), "id"])
    op.create_index("ix_registration_invites_email_lower", "registration_invites", [sa.text("lower(email)")])

    # Журнал листается ключом id: составные индексы отдают фильтр сразу в порядке страницы.
    op.drop_index("ix_audit_log_actor_id", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.create_index("ix_audit_log_actor_id_desc", "audit_log", ["actor_id", sa.text("id DESC")])
    op.create_index("ix_audit_log_target_id_desc", "audit_log", ["target", sa.text("id DESC")])
    op.create_index(
        "ix_audit_log_action_id_desc",
        "audit_log",
        ["action", sa.text("id DESC")],
        postgresql_ops={"action": "varchar_pattern_ops"},
    )

    # Список проектов строится по каталогу: копия полей project.json, которые нужны фильтрам и поиску.
    op.add_column("projects", sa.Column("pinned", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("projects", sa.Column("supervisor_name", sa.String(length=256), nullable=True))
    op.drop_index("ix_projects_owner_org_id", table_name="projects")
    op.create_index("ix_projects_owner_org_updated", "projects", ["owner_org_id", "updated_at"])
    op.create_index("ix_projects_name_lower", "projects", [sa.text("lower(name)")])


def downgrade() -> None:
    op.drop_index("ix_projects_name_lower", table_name="projects")
    op.drop_index("ix_projects_owner_org_updated", table_name="projects")
    op.create_index("ix_projects_owner_org_id", "projects", ["owner_org_id"])
    op.drop_column("projects", "supervisor_name")
    op.drop_column("projects", "pinned")

    op.drop_index("ix_audit_log_action_id_desc", table_name="audit_log")
    op.drop_index("ix_audit_log_target_id_desc", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_id_desc", table_name="audit_log")
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])

    op.drop_index("ix_registration_invites_email_lower", table_name="registration_invites")
    op.drop_index("ix_registration_invites_expires_id", table_name="registration_invites")

    op.drop_index("ix_group_members_group_created", table_name="group_members")
    op.drop_index("ix_org_members_org_role", table_name="org_members")
    op.drop_index("ix_org_members_org_created", table_name="org_members")
    op.drop_index("ix_orgs_name_lower", table_name="orgs")

    # Расширение остаётся: его могли поставить и для других нужд.
    op.execute("DROP INDEX IF EXISTS ix_trgm_users_email")
    op.execute("DROP INDEX IF EXISTS ix_trgm_users_name")
    op.drop_index("ix_users_status_created_at", table_name="users")
    op.drop_index("ix_users_name_lower", table_name="users")
    op.drop_index("ix_users_created_at_id", table_name="users")
