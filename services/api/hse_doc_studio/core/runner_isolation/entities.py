"""Живое состояние кластера для экрана изоляции раннеров: что Студия прочла из Kubernetes API сама.

Всё здесь прочитано в пределах выданных Студии прав: Deployment раннеров из админки (право list уже есть при
установке из админки) и, только с опцией чарта `runner.isolationInfo.readCluster`, NetworkPolicy, ResourceQuota,
LimitRange и метки Pod Security у namespace. Значение `None` у флага значит «не проверялось».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.jobs.deployment import ResourceFigures, SecurityFacts
from hse_doc_studio.core.runner_install.resources import ResourceDefaults


class LiveStatus(StrEnum):
    """Удалось ли прочесть кластер: выключено опцией, всё прочитано, часть, нет прав, нет связи."""

    off = "off"
    ok = "ok"
    partial = "partial"
    forbidden = "forbidden"
    unavailable = "unavailable"


class LookupStatus(StrEnum):
    """Поиск Deployment раннера из админки: нашёлся, нет такого, нет прав, нет связи, неприменимо."""

    ok = "ok"
    not_found = "not_found"
    forbidden = "forbidden"
    unavailable = "unavailable"
    not_applicable = "not_applicable"


class ReinstallReason(StrEnum):
    # Версия раннера старше лимитов (0.14.0): его под и поды сборки поставлены без них.
    before_limits = "before_limits"
    # Под раннера в Kubernetes без limits CPU и памяти (по живому Deployment или по отчёту раннера).
    no_pod_limits = "no_pod_limits"


class RunnerOrigin(StrEnum):
    """Откуда раннер: чарт Helm, установка из админки, иное (вручную, по SSH, docker)."""

    chart = "chart"
    ui = "ui"
    other = "other"


@dataclass(frozen=True)
class NamespaceSecurity:
    """Метки Pod Security Admission у namespace (`pod-security.kubernetes.io/*`); пусто значит метки нет."""

    namespace: str
    enforce: str | None = None
    enforce_version: str | None = None
    warn: str | None = None
    audit: str | None = None


@dataclass(frozen=True)
class LiveQuota:
    name: str
    hard: dict[str, str] = field(default_factory=dict)
    used: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LiveLimitRange:
    name: str
    default: dict[str, str] = field(default_factory=dict)
    default_request: dict[str, str] = field(default_factory=dict)
    max: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ClusterTargets:
    """Что проверять: namespace релиза (раннеры и поды сборки раннеров из админки) и namespace подов сборки."""

    release_namespace: str
    build_namespace: str


@dataclass(frozen=True)
class LiveClusterState:
    status: LiveStatus = LiveStatus.off
    checked_at: datetime | None = None
    # NetworkPolicy: deny-all подов сборки (namespace сборки), то же для раннеров из админки (namespace релиза),
    # и egress-политика раннеров. None значит «не проверялось».
    build_deny_all: bool | None = None
    ui_build_deny_all: bool | None = None
    runner_egress: bool | None = None
    # ResourceQuota и LimitRange namespace сборки: None при `*_checked` значит «объекта нет».
    quota_checked: bool = False
    quota: LiveQuota | None = None
    limit_range_checked: bool = False
    limit_range: LiveLimitRange | None = None
    namespaces: tuple[NamespaceSecurity, ...] | None = None


@dataclass(frozen=True)
class LiveDeployment:
    """Deployment раннера, поставленного из админки, как его видит Kubernetes. Env и секреты сюда не попадают."""

    name: str
    namespace: str
    image: str | None = None
    service_account: str | None = None
    ready: bool = False
    resources: ResourceFigures | None = None
    # Лимиты подов сборки этого раннера (значения HSE_RUNNER__K8S__* в манифесте); None у старых установок.
    build_resources: ResourceFigures | None = None
    security: SecurityFacts | None = None


@dataclass(frozen=True)
class DeploymentListing:
    status: LookupStatus
    items: tuple[LiveDeployment, ...] = ()


@dataclass(frozen=True)
class InstallFromUiFacts:
    """Установка раннеров из админки в кластер Студии: настройки из окружения (Helm `runner.installFromUi`)."""

    enabled: bool
    service_account: str
    storage_class: str
    storage_size: str
    defaults: ResourceDefaults
    runner_ephemeral: tuple[str, str]
    build_ephemeral: tuple[str, str]
    namespace: str | None = None
