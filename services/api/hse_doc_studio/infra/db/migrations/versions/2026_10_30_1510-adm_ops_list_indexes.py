"""индексы списков админки эксплуатации: журнал очереди по фильтрам и токены раннеров

Журнал очереди листается курсором по `seq` (новые первыми) с фильтром по одному из столбцов;
составной индекс (столбец, seq DESC) отдаёт страницу без сортировки всей выборки. Индекс по
`project_id` заменён составным: он покрывает и прежние поиски по проекту.

Revision ID: adm_ops_list_indexes
Revises: adm_identity_lists
Create Date: 2026-10-30 15:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "adm_ops_list_indexes"
down_revision: str | None = "adm_identity_lists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_KEYS = ("state", "user_id", "org_id", "runner_id", "project_id")


def upgrade() -> None:
    op.drop_index("ix_jobs_project_id", table_name="jobs")
    for column in _JOB_KEYS:
        op.create_index(f"ix_jobs_{column}_seq", "jobs", [column, sa.text("seq DESC")])
    op.create_index("ix_jobs_queued_at", "jobs", ["queued_at"])
    op.create_index(
        "ix_runner_registration_tokens_created_at", "runner_registration_tokens", [sa.text("created_at DESC")]
    )


def downgrade() -> None:
    op.drop_index("ix_runner_registration_tokens_created_at", table_name="runner_registration_tokens")
    op.drop_index("ix_jobs_queued_at", table_name="jobs")
    for column in reversed(_JOB_KEYS):
        op.drop_index(f"ix_jobs_{column}_seq", table_name="jobs")
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])
