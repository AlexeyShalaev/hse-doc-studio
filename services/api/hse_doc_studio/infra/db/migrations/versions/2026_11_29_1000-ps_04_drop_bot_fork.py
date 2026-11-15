"""Contract: удалены колонки доступа бота `fork_mode` и `fork_url` у служебных доступов Студии шаблонов

Владелец продукта отказался от вклада в официальные паки через бота установки (template-studio.md, 4.7): PR в
официальные паки создают только люди своим аккаунтом GitHub. Колонки добавил `ps_03_pack_official` (выпуск 0.30.0),
данных в них нет: бот нигде не заводился, у всех доступов `fork_mode` false. Код этого выпуска колонками не
пользуется. Api выкатывается одной репликой со стратегией Recreate: прежний под останавливается до миграции.
Заодно убираются настройки установки выключателя и лимита бота (`pack_studio.official_bot_*`), если админ их менял.
Downgrade возвращает колонки прежней схемы со значениями по умолчанию; без настроек 0.30.0 берёт умолчания.

Revision ID: ps_04_drop_bot_fork
Revises: ps_03_pack_official
Create Date: 2026-11-29 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ps_04_drop_bot_fork"
down_revision: str | None = "ps_03_pack_official"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Пометка contract-миграции над колонками (expand/contract, `docs/ru/deploy/operations.md`): какие колонки каких
# таблиц удаляются, ревизия, которая их ввела, и выпуск, в который та вошла. Проверяет `test_migration_expand_contract`.
contract_drop_columns: dict[str, tuple[str, ...]] = {"pack_studio_service_access": ("fork_mode", "fork_url")}
contract_retired_by: str = "ps_03_pack_official"
contract_released_in: str = "0.30.0"


def upgrade() -> None:
    op.execute(
        "DELETE FROM instance_settings "
        "WHERE key IN ('pack_studio.official_bot_enabled', 'pack_studio.official_bot_daily_limit')"
    )
    op.drop_column("pack_studio_service_access", "fork_url")
    op.drop_column("pack_studio_service_access", "fork_mode")


def downgrade() -> None:
    op.add_column(
        "pack_studio_service_access",
        sa.Column("fork_mode", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("pack_studio_service_access", sa.Column("fork_url", sa.Text(), nullable=True))
