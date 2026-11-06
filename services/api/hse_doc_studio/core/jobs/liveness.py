"""Живой общий раннер: по нему решают и доступность сборки, и маршрут задачи."""

from __future__ import annotations

from datetime import datetime, timedelta

from hse_doc_studio.core.jobs.routing import RunnerScope
from hse_doc_studio.core.jobs.runners import Runner

# Раннер живой, если опрашивал сервер не дольше этого назад: предел долгого опроса плюс запас.
DEFAULT_RUNNER_LIVE_WINDOW_S = 60.0


def is_live_shared(runner: Runner, now: datetime, live_window: timedelta) -> bool:
    """Общий раннер, не отозван, не на паузе и опрашивал сервер в пределах окна."""
    # Чужой личный раннер сборку не возьмёт: личные раннеры владельца решает маршрут.
    if runner.scope is not RunnerScope.shared:
        return False
    if runner.revoked_at is not None or runner.paused or runner.last_seen_at is None:
        return False
    return now - runner.last_seen_at <= live_window
