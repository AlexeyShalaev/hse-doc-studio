"""Фоновые задачи маршрутов подписания (docs/design/signing-route.md): автонапоминания подписантам (5.7) и
периодическая сверка маршрутов с проектами (5.5)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI

from hse_doc_studio.api.config import Settings
from hse_doc_studio.core.background import PeriodicTask

if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = structlog.get_logger()

SIGNING_REMINDERS_TASK = "signing_reminders"
SIGNING_ROUTE_SWEEP_TASK = "signing_route_sweep"


def install_signing_reminders(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Автонапоминания о подписи: за сутки до срока и после долгого ожидания; идут только у лидера.

    Регистрируется до старта раннера. Что уже отправлено, записано в самом маршруте, поэтому перезапуск и смена
    лидера напоминаний не повторяют.
    """
    from hse_doc_studio.use_cases.signing_route.reminders import SigningReminderSweeper  # noqa: PLC0415

    async def _remind() -> None:
        sent = await (await container.get(SigningReminderSweeper)).run()
        if sent:
            logger.info("signing_reminders_sent", count=sent)

    app.state.background.register(
        PeriodicTask(name=SIGNING_REMINDERS_TASK, interval_s=cfg.signing_route.reminder_interval_s, run=_remind)
    )


def install_signing_route_sweep(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Сверка идущих маршрутов с документами проектов; идёт только у лидера.

    Страховка для хуков (сборка, запись подписей, синхронизация, восстановление, уход участника): пропущенный хук,
    гибрид с локальной Студией, рестарт между записью файлов и транзакцией. Сверка идемпотентна: маршрут, у
    которого ничего не изменилось, не переписывается, поэтому перезапуск и смена лидера ничего не повторяют.
    """
    from hse_doc_studio.use_cases.signing_route.reconcile import RouteReconciler  # noqa: PLC0415

    async def _sweep() -> None:
        async with container() as scope:
            changed = await (await scope.get(RouteReconciler)).sweep()
        if changed:
            logger.info("signing_routes_reconciled", count=changed)

    app.state.background.register(
        PeriodicTask(name=SIGNING_ROUTE_SWEEP_TASK, interval_s=cfg.signing_route.sweep_interval_s, run=_sweep)
    )
