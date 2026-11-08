"""Что Студия знает о раннерах в кластере из своей конфигурации (Helm): выжимка values для экрана изоляции.

Чарт кладёт её одной JSON-строкой (`HSE_STUDIO__RUNNER_CLUSTER__DECLARED`, шаблон `hds.runnerCluster`); вне Helm её
нет, и экран честно пишет «нет данных конфигурации». Это то, что задано, а не проверенное в кластере.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Values(BaseModel):
    """Форма values Helm: camelCase, лишние ключи (новые в чарте) не мешают старой Студии."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore", frozen=True)


class DeclaredResources(_Values):
    requests: dict[str, str] = Field(default_factory=dict)
    limits: dict[str, str] = Field(default_factory=dict)


class DeclaredChartRunner(_Values):
    enabled: bool = False
    executor: str = "docker"
    replicas: int = 1
    deployment: str = ""
    service_account: str = ""
    resources: DeclaredResources = Field(default_factory=DeclaredResources)
    tmp_size_limit: str = ""
    # pvc, hostPath или emptyDir: том данных раннера.
    storage_kind: str = ""
    storage_class: str = ""
    storage_size: str = ""
    run_as_user: int | None = None


class DeclaredQuota(_Values):
    enabled: bool = False
    hard: dict[str, str] = Field(default_factory=dict)


class DeclaredLimitRange(_Values):
    enabled: bool = False
    default: dict[str, str] = Field(default_factory=dict)
    default_request: dict[str, str] = Field(default_factory=dict)
    max: dict[str, str] = Field(default_factory=dict)


class DeclaredBuild(_Values):
    namespace: str = ""
    resources: DeclaredResources = Field(default_factory=DeclaredResources)
    work_size_limit: str = ""
    tmp_size_limit: str = ""
    active_deadline_seconds: int | None = None
    runtime_class_name: str = ""
    run_as_user: int | None = None
    network_policy: bool = False
    quota: DeclaredQuota = Field(default_factory=DeclaredQuota)
    limit_range: DeclaredLimitRange = Field(default_factory=DeclaredLimitRange)


class DeclaredRunnerEgress(_Values):
    enabled: bool = False
    studio_port: int | None = None
    api_server_cidrs: list[str] = Field(default_factory=list)
    api_server_ports: list[int] = Field(default_factory=list)
    extra_rules: int = 0


class DeclaredCluster(_Values):
    release_namespace: str = ""
    runner: DeclaredChartRunner = Field(default_factory=DeclaredChartRunner)
    build: DeclaredBuild = Field(default_factory=DeclaredBuild)
    runner_egress: DeclaredRunnerEgress = Field(default_factory=DeclaredRunnerEgress)
