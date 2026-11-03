"""Почему облако может или не может пользоваться моделью через Студию: чистая функция без ввода-вывода."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.devices.entities import AiState, EndpointReport


@dataclass(frozen=True)
class RunnerFacts:
    """Что сервер знает о раннере Студии (таблица раннеров), без самого раннера."""

    # RunnerStatus: online, stale, offline, paused, revoked, disabled.
    status: str
    declared: frozenset[str]
    relay_feature: bool


@dataclass(frozen=True)
class ProviderRef:
    id: UUID
    name: str


_RUNNER_PROBLEM = {
    "revoked": AiState.runner_revoked,
    "disabled": AiState.disabled,
    "paused": AiState.runner_paused,
    "offline": AiState.runner_offline,
    "stale": AiState.runner_offline,
}


def endpoint_state(
    *,
    runner: RunnerFacts,
    report: EndpointReport | None,
    provider: ProviderRef | None,
) -> AiState:
    """Состояние одного объявленного адреса: от «раннер недоступен» до «готово»."""
    problem = _RUNNER_PROBLEM.get(runner.status)
    if problem is not None:
        return problem
    if not runner.relay_feature:
        return AiState.not_opened
    if report is not None and report.reachable is False:
        return AiState.endpoint_unreachable
    if report is not None and report.reachable and not report.models:
        return AiState.no_models
    return AiState.no_provider if provider is None else AiState.ready


def overall_state(*, online: bool, paired: bool, runner: RunnerFacts | None, endpoints: tuple[AiState, ...]) -> AiState:
    """Итог по Студии: самый полезный из состояний адресов, а без адресов причина, почему их нет."""
    if not online:
        return AiState.studio_offline
    if not paired or runner is None:
        return AiState.runner_unpaired
    problem = _RUNNER_PROBLEM.get(runner.status)
    if problem is not None:
        return problem
    if not runner.declared or not endpoints:
        return AiState.not_opened
    for wanted in (AiState.ready, AiState.no_provider, AiState.no_models, AiState.endpoint_unreachable):
        if wanted in endpoints:
            return wanted
    return endpoints[0]
