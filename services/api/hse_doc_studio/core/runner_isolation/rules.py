"""Правила экрана изоляции раннеров: устарел ли раннер, стоит ли его переустановить, откуда он."""

from __future__ import annotations

from collections.abc import Iterable

from hse_doc_studio.core.jobs.admin import version_key
from hse_doc_studio.core.jobs.deployment import LIMITS_SINCE_VERSION, RunnerPlatform
from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.core.runner_isolation.declared import DeclaredCluster
from hse_doc_studio.core.runner_isolation.entities import LiveDeployment, ReinstallReason, RunnerOrigin

_UNPARSED = (0, 0, 0, 0)
# Под Deployment называется `<deployment>-<hash ReplicaSet>-<hash пода>`.
_POD_SUFFIX_PARTS = 2


def limits_supported(version: str) -> bool | None:
    """Поставлен ли раннер с лимитами по версии; `None`, если версию не разобрать (сборка из исходников)."""
    key = version_key(version)
    if key == _UNPARSED:
        return None
    return key >= version_key(LIMITS_SINCE_VERSION)


def is_outdated(version: str, studio_version: str) -> bool:
    """Раннер старше самой Студии; неразобранные версии устаревшими не считаются."""
    mine, studio = version_key(version), version_key(studio_version)
    return _UNPARSED not in (mine, studio) and mine < studio


def _deployment_of_pod(pod_name: str, deployment: str) -> bool:
    if not pod_name.startswith(f"{deployment}-"):
        return False
    return len(pod_name[len(deployment) + 1 :].split("-")) == _POD_SUFFIX_PARTS


def match_deployment(runner: Runner, deployments: Iterable[LiveDeployment]) -> LiveDeployment | None:
    """Deployment раннера из админки: по имени пода из отчёта, иначе по имени раннера (его задаёт установка)."""
    items = list(deployments)
    pod_name = runner.deployment.pod_name if runner.deployment is not None else None
    if pod_name:
        found = next((d for d in items if _deployment_of_pod(pod_name, d.name)), None)
        if found is not None:
            return found
    return next((d for d in items if d.name == runner.name), None)


def runner_origin(
    runner: Runner, live: LiveDeployment | None, declared: DeclaredCluster | None, ui_service_account: str
) -> RunnerOrigin | None:
    """Откуда раннер; без отчёта и без живого Deployment неизвестно (`None`)."""
    if live is not None:
        return RunnerOrigin.ui
    report = runner.deployment
    if report is None:
        return None
    if ui_service_account and report.service_account == ui_service_account:
        return RunnerOrigin.ui
    chart = declared.runner if declared is not None else None
    if chart is not None and chart.enabled:
        if chart.service_account and report.service_account == chart.service_account:
            return RunnerOrigin.chart
        if chart.deployment and report.pod_name and _deployment_of_pod(report.pod_name, chart.deployment):
            return RunnerOrigin.chart
    return RunnerOrigin.other


def reinstall_reasons(runner: Runner, live: LiveDeployment | None) -> tuple[ReinstallReason, ...]:
    """Почему раннер стоит переустановить, чтобы применились лимиты; пусто, если всё на месте или не узнать."""
    reasons: list[ReinstallReason] = []
    if limits_supported(runner.version) is False:
        reasons.append(ReinstallReason.before_limits)
    report = runner.deployment
    if live is not None:
        unlimited = live.resources is None or not live.resources.has_limits
    elif report is not None and report.platform is RunnerPlatform.kubernetes:
        unlimited = report.resources is not None and not report.resources.has_limits
    else:
        unlimited = False
    if unlimited:
        reasons.append(ReinstallReason.no_pod_limits)
    return tuple(reasons)
