"""mail_outbox очищена и выведена из употребления: неушедшие письма видны в журнале писем mail_log (mail-log.md, L7)

Код этого выпуска таблицу не читает и не пишет, но прежняя версия api во время обновления ещё пишет в неё, поэтому
сама таблица удаляется contract-миграцией следующего выпуска (expand/contract). Строки не переносятся: в них не было
ни ссылки, ни языка, ни итога. Они стираются сразу, потому что ни чистка `auth_cleanup`, ни стирание человека их
больше не трогают, а адрес получателя это персональные данные.

Revision ID: ml_02_clear_mail_outbox
Revises: ml_01_mail_log
Create Date: 2026-11-17 11:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "ml_02_clear_mail_outbox"
down_revision: str | None = "ml_01_mail_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM mail_outbox")


def downgrade() -> None:
    # Стёртые строки не вернуть, и прежней версии они не нужны: без них она просто не покажет старых записей.
    pass
