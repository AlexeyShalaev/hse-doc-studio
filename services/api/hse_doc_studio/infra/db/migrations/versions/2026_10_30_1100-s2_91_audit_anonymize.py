"""audit_log_anonymize: единственный путь обезличивания журнала при удалении человека

Revision ID: s2_91_audit_anonymize
Revises: s2_50_orgs
Create Date: 2026-10-30 11:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "s2_91_audit_anonymize"
down_revision: str | None = "s2_50_orgs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# UPDATE пропускается только внутри audit_log_anonymize (флаг транзакции), DELETE только внутри audit_log_purge.
_GUARD_WITH_ANONYMIZE = """
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('hse.audit_purge', true) = 'on' THEN
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' AND current_setting('hse.audit_anonymize', true) = 'on' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = 'insufficient_privilege';
END;
$$
"""

_GUARD_WITH_PURGE = """
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('hse.audit_purge', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = 'insufficient_privilege';
END;
$$
"""

# Заменяет id человека в actor_id и target псевдонимом и убирает из details личные поля;
# сами события, их время и действия остаются. Роли приложения достаточно EXECUTE на функцию.
_ANONYMIZE = """
CREATE FUNCTION audit_log_anonymize(subject text, pseudonym text) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    changed bigint;
BEGIN
    PERFORM set_config('hse.audit_anonymize', 'on', true);
    UPDATE audit_log SET
        actor_id = CASE WHEN actor_id = subject THEN pseudonym ELSE actor_id END,
        target = CASE WHEN target = subject THEN pseudonym ELSE target END,
        details = details - 'email' - 'name' - 'ip' - 'user_agent' - 'to'
    WHERE actor_id = subject OR target = subject;
    GET DIAGNOSTICS changed = ROW_COUNT;
    PERFORM set_config('hse.audit_anonymize', 'off', true);
    RETURN changed;
END;
$$
"""


def upgrade() -> None:
    op.execute(_GUARD_WITH_ANONYMIZE)
    op.execute(_ANONYMIZE)
    op.execute("REVOKE ALL ON FUNCTION audit_log_anonymize(text, text) FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP FUNCTION audit_log_anonymize(text, text)")
    op.execute(_GUARD_WITH_PURGE)
