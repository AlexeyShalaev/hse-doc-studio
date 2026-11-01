"""Настройки сборки для раннера: из его окружения, а не из пользовательского config.json."""

from __future__ import annotations

from typing import Any

from hse_doc_studio.infra.runner.config import RunnerConfig


class RunnerSettingsRepository:
    """`ISettingsRepository` только для чтения: слоты сборки это число одновременных задач раннера.

    `latex_passes` здесь нет сознательно: api кладёт пользовательское значение в нагрузку задачи.
    """

    def __init__(self, config: RunnerConfig) -> None:
        self._config = config

    async def get(self) -> dict[str, Any]:
        return {"max_concurrent_compiles": self._config.concurrency}

    async def save(self, settings: dict[str, Any]) -> None:
        raise RuntimeError("runner settings come from the environment and cannot be saved")
