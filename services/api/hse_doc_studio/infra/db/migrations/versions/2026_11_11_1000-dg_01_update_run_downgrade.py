"""update_run_downgrade: вид запуска автообновления «откат на выбранную версию»

Revision ID: dg_01_update_run_downgrade
Revises: ms_01_model_servers
Create Date: 2026-11-11 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "dg_01_update_run_downgrade"
down_revision: str | None = "ms_01_model_servers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_OLD_KINDS = ("update", "rollback")
_NEW_KINDS = (*_OLD_KINDS, "downgrade")


def _replace_kind_check(kinds: tuple[str, ...]) -> None:
    """Расширение списка допустимых значений: прежняя версия api новых значений не пишет, ей это не мешает."""
    op.drop_constraint(op.f("ck_update_runs_kind"), "update_runs", type_="check")
    op.create_check_constraint(op.f("ck_update_runs_kind"), "update_runs", f"kind IN {kinds!r}")


def upgrade() -> None:
    _replace_kind_check(_NEW_KINDS)


def downgrade() -> None:
    op.execute("DELETE FROM update_runs WHERE kind = 'downgrade'")
    _replace_kind_check(_OLD_KINDS)
