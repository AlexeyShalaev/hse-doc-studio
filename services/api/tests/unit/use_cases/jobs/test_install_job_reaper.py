from __future__ import annotations

from fastapi import FastAPI
from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.observability.install import install_job_reaper, install_runner_pairings_purge


class _Runner:
    def __init__(self) -> None:
        self.tasks: list[object] = []

    def register(self, task: object) -> None:
        self.tasks.append(task)


def test__install_job_reaper__registers_periodic_task() -> None:
    app = FastAPI()
    app.state.background = _Runner()
    cfg = Settings()

    install_job_reaper(app, None, cfg)  # type: ignore[arg-type]

    (task,) = app.state.background.tasks
    assert task.name == "job_reaper"  # type: ignore[attr-defined]
    assert task.interval_s == cfg.jobs.reaper_interval_s  # type: ignore[attr-defined]


def test__install_runner_pairings_purge__registers_periodic_task() -> None:
    app = FastAPI()
    app.state.background = _Runner()

    install_runner_pairings_purge(app, None)  # type: ignore[arg-type]

    (task,) = app.state.background.tasks
    assert task.name == "runner_pairings_purge"  # type: ignore[attr-defined]
    assert task.interval_s == 600.0  # type: ignore[attr-defined]
