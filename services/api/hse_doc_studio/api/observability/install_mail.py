"""Фоновая задача журнала писем (docs/design/mail-log.md, раздел 14, V9): автоповтор временных сбоев."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI

from hse_doc_studio.core.background import PeriodicTask

if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = structlog.get_logger()

MAIL_RETRY_TASK = "mail_retry"
# Шаг очереди: самая короткая пауза автоповтора минута, так что письмо уходит не позже чем через 15 с после срока.
MAIL_RETRY_INTERVAL_S = 15.0


def install_mail_retry(app: FastAPI, container: AsyncContainer) -> None:
    """Созревшие автоповторы писем; идёт только у лидера. Очередь лежит в базе с арендой, поэтому перезапуск и
    смена лидера писем не теряют, а письмо, взятое упавшим процессом, повторит следующий проход."""
    from hse_doc_studio.use_cases.mail.dispatch import MailDispatcher  # noqa: PLC0415

    async def _retry() -> None:
        tried = await (await container.get(MailDispatcher)).retry_due()
        if tried:
            logger.info("mail_retries_tried", count=tried)

    app.state.background.register(PeriodicTask(name=MAIL_RETRY_TASK, interval_s=MAIL_RETRY_INTERVAL_S, run=_retry))
