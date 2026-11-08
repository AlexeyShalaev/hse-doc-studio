"""Как развёрнут раннер: что он сообщает о себе серверу (`POST /deployment`) для экрана админки.

Отчёт описывает исполнителя, namespace и ServiceAccount пода, requests и limits самого раннера и подов сборки,
и контекст безопасности. Секретов в нём нет: ни токенов, ни адресов с учётными данными, ни переменных окружения.
Раннер недоверенный, поэтому длины строк и чисел ограничены здесь же, а экран показывает отчёт как «сообщил
раннер», а не как проверенный факт.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# С этой версии чарт и установка из админки ставят раннерам и подам сборки requests и limits
# (CPU, память, эфемерный диск) и усиленный securityContext. Раннер старше стоит переустановить.
LIMITS_SINCE_VERSION = "0.14.0"

MAX_NAME = 253
MAX_QUANTITY = 32
MAX_IMAGE = 512
MAX_DEADLINE_S = 7 * 24 * 3600
MAX_PIDS = 1 << 22
MAX_UID = (1 << 31) - 1


class BuildExecutor(StrEnum):
    docker = "docker"
    kubernetes = "kubernetes"


class RunnerPlatform(StrEnum):
    """Где идёт сам процесс раннера: под Kubernetes, контейнер или обычный хост."""

    kubernetes = "kubernetes"
    container = "container"
    host = "host"


class ResourceSource(StrEnum):
    """Откуда числа: downward API пода, cgroup процесса, настройки раннера или живой объект кластера."""

    pod = "pod"
    cgroup = "cgroup"
    config = "config"
    cluster = "cluster"


def _check_text(value: str | None, limit: int, field: str) -> None:
    if value is not None and (not value or len(value) > limit):
        raise ValueError(f"{field} must be 1..{limit} characters")


def _check_int(value: int | None, low: int, high: int, field: str) -> None:
    if value is not None and not low <= value <= high:
        raise ValueError(f"{field} must be within {low}..{high}")


@dataclass(frozen=True)
class ResourceFigures:
    """requests и limits одного пода или контейнера строками Kubernetes; `None` значит «не задано или неизвестно»."""

    cpu_request: str | None = None
    cpu_limit: str | None = None
    memory_request: str | None = None
    memory_limit: str | None = None
    ephemeral_request: str | None = None
    ephemeral_limit: str | None = None
    source: ResourceSource = ResourceSource.config

    def __post_init__(self) -> None:
        for name in (
            "cpu_request",
            "cpu_limit",
            "memory_request",
            "memory_limit",
            "ephemeral_request",
            "ephemeral_limit",
        ):
            _check_text(getattr(self, name), MAX_QUANTITY, name)

    @property
    def has_limits(self) -> bool:
        return self.cpu_limit is not None and self.memory_limit is not None


@dataclass(frozen=True)
class SecurityFacts:
    """Контекст безопасности: у самого раннера наблюдаемый (/proc), у подов сборки из манифеста."""

    run_as_non_root: bool | None = None
    run_as_user: int | None = None
    read_only_root: bool | None = None
    no_privilege_escalation: bool | None = None
    seccomp: bool | None = None
    capabilities_dropped: bool | None = None
    automount_token: bool | None = None

    def __post_init__(self) -> None:
        _check_int(self.run_as_user, 0, MAX_UID, "run_as_user")


@dataclass(frozen=True)
class BuildIsolation:
    """Изоляция сборки: под на задачу (kubernetes) или соседний контейнер (docker)."""

    namespace: str | None = None
    image: str | None = None
    resources: ResourceFigures | None = None
    # docker: --network none; kubernetes: None, сеть режет NetworkPolicy, её видно в разделе кластера.
    network_disabled: bool | None = None
    pids_limit: int | None = None
    work_size_limit: str | None = None
    tmp_size_limit: str | None = None
    active_deadline_s: int | None = None
    runtime_class: str | None = None
    security: SecurityFacts | None = None

    def __post_init__(self) -> None:
        _check_text(self.namespace, MAX_NAME, "namespace")
        _check_text(self.image, MAX_IMAGE, "image")
        _check_text(self.work_size_limit, MAX_QUANTITY, "work_size_limit")
        _check_text(self.tmp_size_limit, MAX_QUANTITY, "tmp_size_limit")
        _check_text(self.runtime_class, MAX_NAME, "runtime_class")
        _check_int(self.pids_limit, 1, MAX_PIDS, "pids_limit")
        _check_int(self.active_deadline_s, 1, MAX_DEADLINE_S, "active_deadline_s")


@dataclass(frozen=True)
class RunnerDeployment:
    """Отчёт раннера о себе. Старые раннеры его не шлют: у них в админке «нет данных»."""

    executor: BuildExecutor
    platform: RunnerPlatform
    namespace: str | None = None
    pod_name: str | None = None
    service_account: str | None = None
    resources: ResourceFigures | None = None
    security: SecurityFacts | None = None
    build: BuildIsolation | None = None

    def __post_init__(self) -> None:
        _check_text(self.namespace, MAX_NAME, "namespace")
        _check_text(self.pod_name, MAX_NAME, "pod_name")
        _check_text(self.service_account, MAX_NAME, "service_account")
