"""Выбор оркестратора по режиму политики; настройки процесса (секрет, compose) приходят из конфигурации."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from hse_doc_studio.api.config.autoscale import AutoscaleConfig
from hse_doc_studio.core.jobs.autoscale import AutoscaleMode, AutoscalePolicy, IRunnerOrchestrator
from hse_doc_studio.infra.runner_scaling.compose import ComposeOrchestrator
from hse_doc_studio.infra.runner_scaling.webhook import WebhookOrchestrator


class OrchestratorFactory:
    def __init__(self, cfg: AutoscaleConfig, client_factory: Callable[[], httpx.AsyncClient]) -> None:
        self._cfg = cfg
        self._client_factory = client_factory

    def create(self, policy: AutoscalePolicy) -> IRunnerOrchestrator | None:
        """`None` в режиме `off`: решение только показывается."""
        if policy.mode is AutoscaleMode.webhook and policy.webhook_url:
            secret = self._cfg.webhook_secret.get_secret_value() if self._cfg.webhook_secret else None
            return WebhookOrchestrator(policy.webhook_url, secret, self._client_factory)
        if policy.mode is AutoscaleMode.compose:
            return ComposeOrchestrator(
                self._cfg.compose_service,
                project=self._cfg.compose_project,
                compose_file=self._cfg.compose_file,
                timeout_s=self._cfg.compose_timeout_s,
            )
        return None
