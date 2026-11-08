"""`/api/admin/runners`: как раннер развёрнут и как изолированы раннеры в кластере. Гард задаёт `make_admin_router`.

Конфигурация (Helm и настройки Студии), отчёт раннера и живое состояние кластера идут в ответе раздельно: экран
показывает, откуда взято каждое значение. Секретов в ответах нет.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from hse_doc_studio.api.schemas.runner_isolation import (
    AdminRunnerDeployment,
    AdminRunnerIsolation,
    BuildIsolationView,
    BuildPodsView,
    ChartRunnerView,
    InstallBoundsView,
    InstallFromUiView,
    LimitRangeView,
    LimitValuesView,
    NetworkView,
    PodSecurityView,
    PolicyCheckView,
    QuotaView,
    ResourcesView,
    RunnerEgressView,
    RunnerLiveView,
    RunnerReportView,
    SecurityView,
    StorageView,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.jobs.deployment import BuildIsolation, ResourceFigures, SecurityFacts
from hse_doc_studio.core.jobs.errors import RunnerNotFoundError
from hse_doc_studio.core.runner_install.resources import MIN_QUANTITIES, PodResources
from hse_doc_studio.core.runner_isolation import (
    DeclaredCluster,
    InstallFromUiFacts,
    LiveClusterState,
    LiveLimitRange,
    LiveQuota,
    LiveStatus,
)
from hse_doc_studio.core.runner_isolation.declared import DeclaredLimitRange, DeclaredResources
from hse_doc_studio.use_cases.admin.runner_isolation import RunnerDeploymentUC, RunnerIsolationUC, ui_build_namespace

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}
_KUBERNETES = "kubernetes"


def _resources(figures: ResourceFigures | None) -> ResourcesView | None:
    if figures is None:
        return None
    return ResourcesView(
        cpu_request=figures.cpu_request,
        cpu_limit=figures.cpu_limit,
        memory_request=figures.memory_request,
        memory_limit=figures.memory_limit,
        ephemeral_request=figures.ephemeral_request,
        ephemeral_limit=figures.ephemeral_limit,
        source=figures.source.value,
    )


def _security(facts: SecurityFacts | None) -> SecurityView | None:
    if facts is None:
        return None
    return SecurityView(
        run_as_non_root=facts.run_as_non_root,
        run_as_user=facts.run_as_user,
        read_only_root=facts.read_only_root,
        no_privilege_escalation=facts.no_privilege_escalation,
        seccomp=facts.seccomp,
        capabilities_dropped=facts.capabilities_dropped,
        automount_token=facts.automount_token,
    )


def _build(build: BuildIsolation | None) -> BuildIsolationView | None:
    if build is None:
        return None
    return BuildIsolationView(
        namespace=build.namespace,
        image=build.image,
        resources=_resources(build.resources),
        network_disabled=build.network_disabled,
        pids_limit=build.pids_limit,
        work_size_limit=build.work_size_limit,
        tmp_size_limit=build.tmp_size_limit,
        active_deadline_s=build.active_deadline_s,
        runtime_class=build.runtime_class,
        security=_security(build.security),
    )


@router.get("/runners/{runner_id}/deployment", response_model=AdminRunnerDeployment)
async def runner_deployment(runner_id: str, request: Request, response: Response) -> AdminRunnerDeployment:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(RunnerDeploymentUC)
    try:
        info = await uc.execute(require_actor(), runner_id)
    except RunnerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found") from exc
    runner, report, live = info.runner, info.runner.deployment, info.live
    return AdminRunnerDeployment(
        runner_id=runner.id,
        name=runner.name,
        version=runner.version,
        studio_version=info.studio_version,
        outdated=info.outdated,
        limits_supported=info.limits_supported,
        reinstall=[reason.value for reason in info.reinstall],
        origin=info.origin.value if info.origin is not None else None,
        report=RunnerReportView(
            reported_at=runner.deployment_at,
            executor=report.executor.value,
            platform=report.platform.value,
            namespace=report.namespace,
            pod_name=report.pod_name,
            service_account=report.service_account,
            resources=_resources(report.resources),
            security=_security(report.security),
            build=_build(report.build),
        )
        if report is not None
        else None,
        live=RunnerLiveView(
            name=live.name,
            namespace=live.namespace,
            image=live.image,
            service_account=live.service_account,
            ready=live.ready,
            resources=_resources(live.resources),
            build_resources=_resources(live.build_resources),
            security=_security(live.security),
        )
        if live is not None
        else None,
        live_status=info.live_status.value,
    )


def _declared_resources(values: DeclaredResources) -> ResourcesView:
    return ResourcesView(
        cpu_request=values.requests.get("cpu"),
        cpu_limit=values.limits.get("cpu"),
        memory_request=values.requests.get("memory"),
        memory_limit=values.limits.get("memory"),
        ephemeral_request=values.requests.get("ephemeral-storage"),
        ephemeral_limit=values.limits.get("ephemeral-storage"),
        source="config",
    )


def _pod_resources(pod: PodResources, ephemeral: tuple[str, str]) -> ResourcesView:
    return ResourcesView(
        cpu_request=pod.cpu_request,
        cpu_limit=pod.cpu_limit,
        memory_request=pod.memory_request,
        memory_limit=pod.memory_limit,
        ephemeral_request=ephemeral[0],
        ephemeral_limit=ephemeral[1],
        source="config",
    )


def chart_runner_view(declared: DeclaredCluster) -> ChartRunnerView:
    """securityContext раннера чарта (runner.yaml и runner-kubernetes.yaml): тест сверяет с отрисованным чартом."""
    chart = declared.runner
    kubernetes = chart.executor == _KUBERNETES
    storage_kind = {"pvc": "pvc", "hostPath": "host_path", "emptyDir": "empty_dir"}.get(chart.storage_kind)
    return ChartRunnerView(
        enabled=chart.enabled,
        executor="kubernetes" if kubernetes else "docker",
        replicas=chart.replicas,
        namespace=declared.release_namespace or None,
        service_account=chart.service_account or None,
        resources=_declared_resources(chart.resources),
        tmp_size_limit=chart.tmp_size_limit or None,
        storage=StorageView(
            kind=storage_kind,
            storage_class=chart.storage_class or None,
            size=chart.storage_size or None,
        ),
        security=SecurityView(
            run_as_non_root=True,
            run_as_user=chart.run_as_user,
            read_only_root=kubernetes,
            no_privilege_escalation=True,
            seccomp=True,
            capabilities_dropped=True,
            automount_token=kubernetes,
        ),
        docker_socket=not kubernetes,
    )


def _build_pods(declared: DeclaredCluster) -> BuildPodsView:
    """securityContext подов сборки задаёт раннер (infra/compile/k8s/pod.py), он одинаков для всех."""
    build = declared.build
    return BuildPodsView(
        namespace=build.namespace or declared.release_namespace or None,
        resources=_declared_resources(build.resources),
        work_size_limit=build.work_size_limit or None,
        tmp_size_limit=build.tmp_size_limit or None,
        active_deadline_s=build.active_deadline_seconds,
        runtime_class=build.runtime_class_name or None,
        security=SecurityView(
            run_as_non_root=True,
            run_as_user=build.run_as_user,
            read_only_root=True,
            no_privilege_escalation=True,
            seccomp=True,
            capabilities_dropped=True,
            automount_token=False,
        ),
    )


def _install(install: InstallFromUiFacts, declared: DeclaredCluster | None) -> InstallFromUiView:
    defaults = install.defaults
    return InstallFromUiView(
        enabled=install.enabled,
        namespace=install.namespace or (declared.release_namespace if declared is not None else None) or None,
        build_namespace=ui_build_namespace(declared, install) or None,
        service_account=install.service_account or None,
        storage_class=install.storage_class or None,
        storage_size=install.storage_size,
        runner=_pod_resources(defaults.runner, install.runner_ephemeral),
        build=_pod_resources(defaults.build, install.build_ephemeral),
        bounds=InstallBoundsView(
            max_cpu=defaults.max_cpu,
            max_memory=defaults.max_memory,
            min_runner_cpu=MIN_QUANTITIES["runner_cpu"],
            min_runner_memory=MIN_QUANTITIES["runner_memory"],
            min_build_cpu=MIN_QUANTITIES["build_cpu"],
            min_build_memory=MIN_QUANTITIES["build_memory"],
        ),
    )


def _network(declared: DeclaredCluster, install: InstallFromUiFacts, live: LiveClusterState) -> NetworkView:
    chart_k8s = declared.runner.enabled and declared.runner.executor == _KUBERNETES
    egress = declared.runner_egress
    return NetworkView(
        build_deny_all=PolicyCheckView(declared=chart_k8s and declared.build.network_policy, live=live.build_deny_all),
        ui_build_deny_all=PolicyCheckView(
            declared=install.enabled
            and (declared.ui_build.network_policy if declared.ui_build is not None else declared.build.network_policy),
            live=live.ui_build_deny_all,
        ),
        runner_egress=RunnerEgressView(
            declared=egress.enabled,
            live=live.runner_egress,
            dns=egress.enabled,
            studio_port=egress.studio_port,
            api_server_cidrs=list(egress.api_server_cidrs),
            api_server_ports=list(egress.api_server_ports),
            extra_rules=egress.extra_rules,
        ),
    )


def _limits(values: DeclaredLimitRange) -> LimitValuesView:
    return LimitValuesView(
        default=dict(values.default), default_request=dict(values.default_request), max=dict(values.max)
    )


def _chart_build_ns(declared: DeclaredCluster) -> str:
    return declared.build.namespace or declared.release_namespace


def _ui_separate(declared: DeclaredCluster, install: InstallFromUiFacts) -> str | None:
    """Namespace подов сборки раннеров из админки, если у него свои квота и LimitRange (не тот, что у раннера чарта)."""
    ui_ns = ui_build_namespace(declared, install)
    return ui_ns if install.enabled and ui_ns and ui_ns != _chart_build_ns(declared) else None


def _ui_shares(declared: DeclaredCluster, install: InstallFromUiFacts, flag: str) -> bool:
    """Квота (LimitRange) раннеров из админки стоит в том же namespace, что у раннера чарта: объект один."""
    ui = declared.ui_build
    return ui is not None and getattr(ui, flag) and _ui_separate(declared, install) is None


def _quota_view(
    namespace: str | None, declared: dict[str, str] | None, checked: bool, found: LiveQuota | None
) -> QuotaView:
    return QuotaView(
        namespace=namespace or None,
        declared=declared,
        live_found=(found is not None) if checked else None,
        live_hard=dict(found.hard) if found is not None else None,
        live_used=dict(found.used) if found is not None else None,
    )


def _range_view(
    namespace: str | None, declared: DeclaredLimitRange | None, checked: bool, found: LiveLimitRange | None
) -> LimitRangeView:
    return LimitRangeView(
        namespace=namespace or None,
        declared=_limits(declared) if declared is not None else None,
        live_found=(found is not None) if checked else None,
        live=LimitValuesView(default=found.default, default_request=found.default_request, max=found.max)
        if found is not None
        else None,
    )


def _quota(declared: DeclaredCluster, install: InstallFromUiFacts, live: LiveClusterState) -> QuotaView:
    quota = declared.build.quota
    on = quota.enabled or _ui_shares(declared, install, "quota")
    return _quota_view(_chart_build_ns(declared), dict(quota.hard) if on else None, live.quota_checked, live.quota)


def _limit_range(declared: DeclaredCluster, install: InstallFromUiFacts, live: LiveClusterState) -> LimitRangeView:
    ranges = declared.build.limit_range
    on = ranges.enabled or _ui_shares(declared, install, "limit_range")
    return _range_view(_chart_build_ns(declared), ranges if on else None, live.limit_range_checked, live.limit_range)


def _ui_quota(declared: DeclaredCluster, install: InstallFromUiFacts, live: LiveClusterState) -> QuotaView | None:
    ns = _ui_separate(declared, install)
    if ns is None:
        return None
    on = declared.ui_build is not None and declared.ui_build.quota
    return _quota_view(ns, dict(declared.build.quota.hard) if on else None, live.ui_quota_checked, live.ui_quota)


def _ui_limit_range(
    declared: DeclaredCluster, install: InstallFromUiFacts, live: LiveClusterState
) -> LimitRangeView | None:
    ns = _ui_separate(declared, install)
    if ns is None:
        return None
    on = declared.ui_build is not None and declared.ui_build.limit_range
    return _range_view(ns, declared.build.limit_range if on else None, live.ui_limit_range_checked, live.ui_limit_range)


@router.get("/runners/isolation", response_model=AdminRunnerIsolation)
async def runners_isolation(request: Request, response: Response) -> AdminRunnerIsolation:
    response.headers.update(_NO_STORE)
    info = await (await request.state.dishka_container.get(RunnerIsolationUC)).execute(require_actor())
    declared, live = info.declared, info.live
    chart_k8s = declared is not None and declared.runner.enabled and declared.runner.executor == _KUBERNETES
    return AdminRunnerIsolation(
        config="helm" if declared is not None else "none",
        live_read=live.status.value,
        checked_at=live.checked_at if live.status is not LiveStatus.off else None,
        release_namespace=(declared.release_namespace or None) if declared is not None else None,
        chart_runner=chart_runner_view(declared) if declared is not None else None,
        # Поды сборки чарта есть только у раннера с исполнителем kubernetes.
        build=_build_pods(declared) if declared is not None and chart_k8s else None,
        install_from_ui=_install(info.install, declared),
        network=_network(declared, info.install, live) if declared is not None else None,
        quota=_quota(declared, info.install, live) if declared is not None else None,
        limit_range=_limit_range(declared, info.install, live) if declared is not None else None,
        ui_quota=_ui_quota(declared, info.install, live) if declared is not None else None,
        ui_limit_range=_ui_limit_range(declared, info.install, live) if declared is not None else None,
        pod_security=[
            PodSecurityView(
                namespace=ns.namespace,
                enforce=ns.enforce,
                enforce_version=ns.enforce_version,
                warn=ns.warn,
                audit=ns.audit,
            )
            for ns in live.namespaces
        ]
        if live.namespaces is not None
        else None,
    )
