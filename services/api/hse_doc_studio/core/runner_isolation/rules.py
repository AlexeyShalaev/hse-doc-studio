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


def pod_of_deployment(pod_name: str, deployment: str) -> bool:
    """Под с таким именем создан этим Deployment (`<deployment>-<hash ReplicaSet>-<hash пода>`)."""
    if not pod_name.startswith(f"{deployment}-"):
        return False
    return len(pod_name[len(deployment) + 1 :].split("-")) == _POD_SUFFIX_PARTS


def match_deployment(runner: Runner, deployments: Iterable[LiveDeployment]) -> LiveDeployment | None:
    """Deployment раннера из админки: по имени пода из отчёта, иначе по имени раннера (его задаёт установка)."""
    items = list(deployments)
    pod_name = runner.deployment.pod_name if runner.deployment is not None else None
    if pod_name:
        found = next((d for d in items if pod_of_deployment(pod_name, d.name)), None)
        if found is not None:
            return found
    return next((d for d in items if d.name == runner.name), None)


def _pod_name(runner: Runner) -> str | None:
    return runner.deployment.pod_name if runner.deployment is not None else None


def installed_runner(name: str, runners: Iterable[Runner]) -> Runner | None:
    """Запись в Студии раннера, поставленного из админки под именем `name` (Deployment или контейнер).

    Сначала по поду из отчёта раннера, иначе по имени раннера: его задаёт установка, а переименование в интерфейсе
    отчёт о поде не меняет. Отозванные записи не в счёт: такой установке раннера в Студии уже нет.
    """
    live = [r for r in runners if r.revoked_at is None]
    by_pod = [r for r in live if (pod := _pod_name(r)) is not None and pod_of_deployment(pod, name)]
    found = by_pod or [r for r in live if r.name == name]
    return max(found, key=lambda r: r.last_seen_at or r.created_at, default=None)


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
        if chart.deployment and report.pod_name and pod_of_deployment(report.pod_name, chart.deployment):
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
