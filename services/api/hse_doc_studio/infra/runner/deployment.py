"""Отчёт раннера о том, как он развёрнут: из его настроек, downward API пода, cgroup и /proc своего процесса.

Ничего секретного сюда не попадает: ни токены, ни переменные окружения целиком, ни адреса. Всё, что не удалось
узнать (не Linux, нет cgroup v2, старый манифест без downward API), остаётся `None`, а экран показывает «нет данных».
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from hse_doc_studio.core.jobs.deployment import (
    BuildExecutor,
    BuildIsolation,
    ResourceFigures,
    ResourceSource,
    RunnerDeployment,
    RunnerPlatform,
    SecurityFacts,
)
from hse_doc_studio.infra.compile.docker_compile_executor import ExecutorLimits
from hse_doc_studio.infra.compile.k8s.config import SA_DIR
from hse_doc_studio.infra.compile.k8s.pod import build_isolation
from hse_doc_studio.infra.runner.config import BuildExecutorKind, RunnerConfig, RunnerPodInfo

logger = logging.getLogger(__name__)

_CGROUP_PERIOD_PARTS = 2


@dataclass(frozen=True)
class HostView:
    """Где смотреть на свой процесс; тесты подменяют пути и окружение."""

    proc_status: Path = Path("/proc/self/status")
    cgroup_root: Path = Path("/sys/fs/cgroup")
    sa_dir: Path = SA_DIR
    container_markers: tuple[Path, ...] = (Path("/.dockerenv"), Path("/run/.containerenv"))
    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    uid: int | None = field(default_factory=lambda: os.getuid() if hasattr(os, "getuid") else None)
    root: str = "/"


def collect_deployment(config: RunnerConfig, view: HostView | None = None) -> RunnerDeployment:
    host = view or HostView()
    in_cluster = bool(host.env.get("KUBERNETES_SERVICE_HOST"))
    platform = (
        RunnerPlatform.kubernetes
        if in_cluster
        else RunnerPlatform.container
        if any(marker.exists() for marker in host.container_markers)
        else RunnerPlatform.host
    )
    pod = config.pod
    namespace = pod.namespace or (_read(host.sa_dir / "namespace") if in_cluster else None)
    pod_name = pod.name or (host.env.get("HOSTNAME") if in_cluster else None)
    return RunnerDeployment(
        executor=BuildExecutor(config.executor.value),
        platform=platform,
        namespace=namespace or None,
        pod_name=pod_name or None,
        service_account=pod.service_account or None,
        resources=_own_resources(pod, host),
        security=_own_security(host, in_cluster=in_cluster),
        build=_build(config),
    )


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _own_resources(pod: RunnerPodInfo, host: HostView) -> ResourceFigures | None:
    """requests и limits пода из downward API; без него только лимиты по cgroup v2 (None значит «без лимита»)."""
    figures = (
        pod.cpu_request_m,
        pod.cpu_limit_m,
        pod.memory_request_mi,
        pod.memory_limit_mi,
        pod.ephemeral_request_mi,
        pod.ephemeral_limit_mi,
    )
    if any(value is not None for value in figures):
        return ResourceFigures(
            cpu_request=_milli(pod.cpu_request_m),
            cpu_limit=_milli(pod.cpu_limit_m),
            memory_request=_mebi(pod.memory_request_mi),
            memory_limit=_mebi(pod.memory_limit_mi),
            ephemeral_request=_mebi(pod.ephemeral_request_mi),
            ephemeral_limit=_mebi(pod.ephemeral_limit_mi),
            source=ResourceSource.pod,
        )
    cpu = _read(host.cgroup_root / "cpu.max")
    memory = _read(host.cgroup_root / "memory.max")
    if cpu is None and memory is None:
        return None
    return ResourceFigures(
        cpu_limit=_cgroup_cpu(cpu), memory_limit=_cgroup_memory(memory), source=ResourceSource.cgroup
    )


def _milli(value: int | None) -> str | None:
    return None if value is None else f"{value}m"


def _mebi(value: int | None) -> str | None:
    return None if value is None else f"{value}Mi"


def _cgroup_cpu(raw: str | None) -> str | None:
    """`cpu.max`: «квота период» в микросекундах; `max` значит без лимита."""
    parts = (raw or "").split()
    if len(parts) != _CGROUP_PERIOD_PARTS or parts[0] == "max":
        return None
    try:
        quota, period = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return f"{quota * 1000 // period}m" if period > 0 else None


def _cgroup_memory(raw: str | None) -> str | None:
    if raw is None or raw == "max":
        return None
    try:
        return f"{int(raw) // (1024 * 1024)}Mi"
    except ValueError:
        return None


def _status_fields(path: Path) -> dict[str, str]:
    text = _read(path)
    if text is None:
        return {}
    found: dict[str, str] = {}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        found[key.strip()] = value.strip()
    return found


def _flag(fields: Mapping[str, str], key: str, *, truthy: str) -> bool | None:
    value = fields.get(key)
    return None if value is None else value == truthy


def _read_only_root(root: str) -> bool | None:
    try:
        return bool(os.statvfs(root).f_flag & os.ST_RDONLY)
    except (AttributeError, OSError):
        return None


def _own_security(host: HostView, *, in_cluster: bool) -> SecurityFacts:
    """Наблюдаемое у своего процесса: uid, NoNewPrivs, seccomp, ограничивающий набор capabilities, корень ФС."""
    fields = _status_fields(host.proc_status)
    seccomp = fields.get("Seccomp")
    bounding = fields.get("CapBnd")
    try:
        dropped = None if bounding is None else int(bounding, 16) == 0
    except ValueError:
        dropped = None
    return SecurityFacts(
        run_as_non_root=None if host.uid is None else host.uid != 0,
        run_as_user=host.uid,
        read_only_root=_read_only_root(host.root),
        no_privilege_escalation=_flag(fields, "NoNewPrivs", truthy="1"),
        seccomp=None if seccomp is None else seccomp != "0",
        capabilities_dropped=dropped,
        automount_token=(host.sa_dir / "token").exists() if in_cluster else None,
    )


def _build(config: RunnerConfig) -> BuildIsolation:
    if config.executor is BuildExecutorKind.kubernetes:
        k8s = config.k8s
        return build_isolation(k8s, k8s.resolved_namespace(), k8s.image or config.tex_image)
    return _docker_build(config.executor_limits(), config.tex_image)


def _docker_build(limits: ExecutorLimits | None, image: str) -> BuildIsolation:
    """Соседний контейнер `docker run` с флагами `ExecutorLimits.docker_args`; без изоляции все поля пустые."""
    if limits is None:
        return BuildIsolation(image=image or None, network_disabled=False)
    uid = _uid_of(limits.user)
    return BuildIsolation(
        image=image or None,
        resources=ResourceFigures(
            cpu_limit=f"{limits.cpus:g}" if limits.cpus is not None else None,
            memory_limit=limits.memory,
            source=ResourceSource.config,
        ),
        network_disabled=limits.network_none,
        pids_limit=limits.pids_limit,
        tmp_size_limit=limits.tmpfs_tmp if limits.read_only_rootfs else None,
        security=SecurityFacts(
            run_as_non_root=uid is not None and uid != 0,
            run_as_user=uid,
            read_only_root=limits.read_only_rootfs,
            no_privilege_escalation=limits.no_new_privileges,
            capabilities_dropped=limits.cap_drop_all,
        ),
    )


def _uid_of(user: str | None) -> int | None:
    if not user:
        return None
    head = user.split(":", 1)[0]
    return int(head) if head.isdigit() else None
