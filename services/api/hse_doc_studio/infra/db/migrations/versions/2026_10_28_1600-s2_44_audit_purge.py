"""audit_log_purge: единственный путь стирания журнала по сроку хранения

Revision ID: s2_44_audit_purge
Revises: 0007
Create Date: 2026-10-28 16:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "s2_44_audit_purge"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Построчный DELETE пропускается только внутри audit_log_purge, где выставлен флаг транзакции.
# UPDATE и TRUNCATE запрещены по-прежнему.
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

_GUARD_ORIGINAL = """
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = 'insufficient_privilege';
END;
$$
"""

# SECURITY DEFINER: роли приложения не нужно право DELETE на таблицу, достаточно EXECUTE на функцию.
_PURGE = """
CREATE FUNCTION audit_log_purge(cutoff timestamptz) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE
    removed bigint;
BEGIN
    PERFORM set_config('hse.audit_purge', 'on', true);
    DELETE FROM audit_log WHERE at < cutoff;
    GET DIAGNOSTICS removed = ROW_COUNT;
    PERFORM set_config('hse.audit_purge', 'off', true);
    RETURN removed;
END;
$$
"""


def upgrade() -> None:
    op.execute(_GUARD_WITH_PURGE)
    op.execute(_PURGE)
    op.execute("REVOKE ALL ON FUNCTION audit_log_purge(timestamptz) FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP FUNCTION audit_log_purge(timestamptz)")
    op.execute(_GUARD_ORIGINAL)
