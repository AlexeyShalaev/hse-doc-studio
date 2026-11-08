"""Админка: как раннер развёрнут и как изолированы раннеры в кластере (`/api/admin/runners/...`).

Формы описаны в contracts/server (AdminRunnerDeployment, AdminRunnerIsolation). Секретов нет ни в одной:
ни токенов, ни DSN, ни ключей, ни переменных окружения раннера.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from hse_doc_studio.api.schemas.common import StrictModel

ResourceSourceName = Literal["pod", "cgroup", "config", "cluster"]


class ResourcesView(StrictModel):
    cpu_request: str | None
    cpu_limit: str | None
    memory_request: str | None
    memory_limit: str | None
    ephemeral_request: str | None
    ephemeral_limit: str | None
    source: ResourceSourceName


class SecurityView(StrictModel):
    run_as_non_root: bool | None
    run_as_user: int | None
    read_only_root: bool | None
    no_privilege_escalation: bool | None
    seccomp: bool | None
    capabilities_dropped: bool | None
    automount_token: bool | None


class BuildIsolationView(StrictModel):
    namespace: str | None
    image: str | None
    resources: ResourcesView | None
    network_disabled: bool | None
    pids_limit: int | None
    work_size_limit: str | None
    tmp_size_limit: str | None
    active_deadline_s: int | None
    runtime_class: str | None
    security: SecurityView | None


class RunnerReportView(StrictModel):
    reported_at: datetime | None
    executor: Literal["docker", "kubernetes"]
    platform: Literal["kubernetes", "container", "host"]
    namespace: str | None
    pod_name: str | None
    service_account: str | None
    resources: ResourcesView | None
    security: SecurityView | None
    build: BuildIsolationView | None


class RunnerLiveView(StrictModel):
    name: str
    namespace: str
    image: str | None
    service_account: str | None
    ready: bool
    resources: ResourcesView | None
    build_resources: ResourcesView | None
    security: SecurityView | None


class AdminRunnerDeployment(StrictModel):
    runner_id: str
    name: str
    version: str
    studio_version: str
    outdated: bool
    # Поставлен ли с лимитами по версии (0.14.0 и новее); null, если версия не разобрана.
    limits_supported: bool | None
    reinstall: list[Literal["before_limits", "no_pod_limits"]]
    origin: Literal["chart", "ui", "other"] | None
    # Что раннер сообщил о себе; null у старых раннеров («нет данных»).
    report: RunnerReportView | None
    # Deployment раннера из админки, прочитанный из кластера.
    live: RunnerLiveView | None
    live_status: Literal["ok", "not_found", "forbidden", "unavailable", "not_applicable"]


class StorageView(StrictModel):
    kind: Literal["pvc", "host_path", "empty_dir"] | None
    storage_class: str | None
    size: str | None


class ChartRunnerView(StrictModel):
    enabled: bool
    executor: Literal["docker", "kubernetes"]
    replicas: int
    namespace: str | None
    service_account: str | None
    resources: ResourcesView
    tmp_size_limit: str | None
    storage: StorageView
    security: SecurityView
    # Исполнитель docker монтирует docker.sock узла: это root на узле.
    docker_socket: bool


class BuildPodsView(StrictModel):
    namespace: str | None
    resources: ResourcesView
    work_size_limit: str | None
    tmp_size_limit: str | None
    active_deadline_s: int | None
    runtime_class: str | None
    security: SecurityView


class InstallBoundsView(StrictModel):
    max_cpu: str
    max_memory: str
    min_runner_cpu: str
    min_runner_memory: str
    min_build_cpu: str
    min_build_memory: str


class InstallFromUiView(StrictModel):
    enabled: bool
    namespace: str | None
    # Namespace подов сборки таких раннеров: свой (runner.installFromUi.buildNamespace) или namespace раннера.
    build_namespace: str | None
    service_account: str | None
    storage_class: str | None
    storage_size: str
    runner: ResourcesView
    build: ResourcesView
    bounds: InstallBoundsView


class PolicyCheckView(StrictModel):
    # null: в конфигурации об этом ничего нет (не Helm).
    declared: bool | None
    # null: в кластере не проверялось.
    live: bool | None


class RunnerEgressView(StrictModel):
    declared: bool | None
    live: bool | None
    dns: bool
    studio_port: int | None
    api_server_cidrs: list[str]
    api_server_ports: list[int]
    extra_rules: int


class NetworkView(StrictModel):
    build_deny_all: PolicyCheckView
    ui_build_deny_all: PolicyCheckView
    runner_egress: RunnerEgressView


class QuotaView(StrictModel):
    namespace: str | None
    # null: квота в конфигурации выключена.
    declared: dict[str, str] | None
    # Проверено в кластере: live_found false значит «объекта нет»; null значит «не проверялось».
    live_found: bool | None
    live_hard: dict[str, str] | None
    live_used: dict[str, str] | None


class LimitValuesView(StrictModel):
    default: dict[str, str]
    default_request: dict[str, str]
    max: dict[str, str]


class LimitRangeView(StrictModel):
    namespace: str | None
    declared: LimitValuesView | None
    live_found: bool | None
    live: LimitValuesView | None


class PodSecurityView(StrictModel):
    namespace: str
    enforce: str | None
    enforce_version: str | None
    warn: str | None
    audit: str | None


class AdminRunnerIsolation(StrictModel):
    # helm: выжимка values есть; none: Студия не из чарта, о кластере знает только настройки установки.
    config: Literal["helm", "none"]
    live_read: Literal["off", "ok", "partial", "forbidden", "unavailable"]
    checked_at: datetime | None
    release_namespace: str | None
    chart_runner: ChartRunnerView | None
    build: BuildPodsView | None
    install_from_ui: InstallFromUiView
    network: NetworkView | None
    quota: QuotaView | None
    limit_range: LimitRangeView | None
    # Квота и LimitRange namespace подов сборки раннеров из админки, если он не тот, что у `quota` и `limit_range`.
    ui_quota: QuotaView | None
    ui_limit_range: LimitRangeView | None
    # null: не проверялось (нет права читать namespace).
    pod_security: list[PodSecurityView] | None
