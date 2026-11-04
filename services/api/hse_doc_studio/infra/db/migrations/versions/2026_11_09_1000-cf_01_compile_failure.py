"""compile_records: код и деталь причины неудачной сборки

Revision ID: cf_01_compile_failure
Revises: cd_01_connected_devices
Create Date: 2026-11-09 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cf_01_compile_failure"
down_revision: str | None = "cd_01_connected_devices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("compile_records", sa.Column("error_code", sa.String(length=64), nullable=True))
    op.add_column("compile_records", sa.Column("error_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("compile_records", "error_detail")
    op.drop_column("compile_records", "error_code")
