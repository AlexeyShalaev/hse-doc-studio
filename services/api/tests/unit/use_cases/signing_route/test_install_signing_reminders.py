"""Регистрация периодической задачи автонапоминаний (docs/design/signing-route.md, раздел 5.7)."""

from __future__ import annotations

from fastapi import FastAPI
from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.config.signing_route import SigningRouteConfig
from hse_doc_studio.api.observability.install_signing import install_signing_reminders
from hse_doc_studio.core.background import PeriodicTask


class _Runner:
    def __init__(self) -> None:
        self.tasks: list[PeriodicTask] = []

    def register(self, task: PeriodicTask) -> None:
        self.tasks.append(task)


class _Sweeper:
    def __init__(self) -> None:
        self.runs = 0

    async def run(self) -> int:
        self.runs += 1
        return 2


class _Container:
    def __init__(self, sweeper: _Sweeper) -> None:
        self._sweeper = sweeper

    async def get(self, _port: object) -> _Sweeper:
        return self._sweeper


async def test__install_signing_reminders__registers_periodic_task_that_runs_the_sweeper() -> None:
    app = FastAPI()
    app.state.background = _Runner()
    cfg = Settings(signing_route=SigningRouteConfig(reminder_interval_s=120))
    sweeper = _Sweeper()

    install_signing_reminders(app, _Container(sweeper), cfg)  # type: ignore[arg-type]

    (task,) = app.state.background.tasks
    assert (task.name, task.interval_s, task.run_on_start) == ("signing_reminders", 120.0, False)
    await task.run()
    assert sweeper.runs == 1


def test__signing_route_settings__defaults_match_the_design() -> None:
    cfg = Settings().signing_route

    assert (cfg.reminder_before_deadline_hours, cfg.reminder_waiting_days, cfg.reminder_max_auto) == (24.0, 3.0, 3)
    assert cfg.reminder_interval_s == 900.0
