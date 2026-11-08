"""Сборщики для экрана изоляции раннеров: настройки установки из админки, выжимка Helm, отчёт раннера."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hse_doc_studio.core.jobs.codec import decode
from hse_doc_studio.core.jobs.deployment import RunnerDeployment
from hse_doc_studio.core.runner_install.resources import (
    BUILD_EPHEMERAL,
    RUNNER_EPHEMERAL,
    PodResources,
    ResourceDefaults,
)
from hse_doc_studio.core.runner_isolation import DeclaredCluster, InstallFromUiFacts

_RUNNER_FIXTURES = Path(__file__).resolve().parents[4] / "contracts" / "runner" / "fixtures" / "RunnerDeploymentBody"


def make_install_facts(
    *, enabled: bool = False, service_account: str = "", build_namespace: str | None = None
) -> InstallFromUiFacts:
    return InstallFromUiFacts(
        enabled=enabled,
        service_account=service_account,
        storage_class="",
        storage_size="5Gi",
        defaults=ResourceDefaults(
            runner=PodResources(cpu_request="100m", cpu_limit="1", memory_request="256Mi", memory_limit="2Gi"),
            build=PodResources(cpu_request="500m", cpu_limit="2", memory_request="1Gi", memory_limit="4Gi"),
        ),
        runner_ephemeral=RUNNER_EPHEMERAL,
        build_ephemeral=BUILD_EPHEMERAL,
        build_namespace=build_namespace,
    )


def make_declared(**overrides: Any) -> DeclaredCluster:
    """Выжимка values, как её пишет чарт (camelCase): kubernetes-раннер, отдельный namespace сборки с квотой."""
    body: dict[str, Any] = {
        "releaseNamespace": "studio",
        "runner": {
            "enabled": True,
            "executor": "kubernetes",
            "replicas": 1,
            "deployment": "rel-runner",
            "serviceAccount": "rel-runner",
            "resources": {
                "requests": {"cpu": "100m", "memory": "256Mi", "ephemeral-storage": "128Mi"},
                "limits": {"cpu": "1", "memory": "2Gi", "ephemeral-storage": "2Gi"},
            },
            "tmpSizeLimit": "1Gi",
            "storageKind": "pvc",
            "storageClass": "",
            "storageSize": "10Gi",
            "runAsUser": 1000,
        },
        "build": {
            "namespace": "builds",
            "resources": {
                "requests": {"cpu": "500m", "memory": "1Gi", "ephemeral-storage": "1Gi"},
                "limits": {"cpu": "2", "memory": "4Gi", "ephemeral-storage": "4Gi"},
            },
            "workSizeLimit": "2Gi",
            "tmpSizeLimit": "1Gi",
            "activeDeadlineSeconds": 1800,
            "runtimeClassName": "",
            "runAsUser": 1000,
            "networkPolicy": True,
            "quota": {"enabled": True, "hard": {"pods": "20", "limits.memory": "80Gi"}},
            "limitRange": {"enabled": False, "default": {}, "defaultRequest": {}, "max": {}},
        },
        "runnerEgress": {
            "enabled": True,
            "studioPort": 8000,
            "apiServerCidrs": ["10.0.0.5/32"],
            "apiServerPorts": [443],
            "extraRules": 2,
        },
        **overrides,
    }
    return DeclaredCluster.model_validate(body)


def report_body(name: str = "kubernetes") -> dict[str, Any]:
    data: dict[str, Any] = json.loads((_RUNNER_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return data


def make_report(name: str = "kubernetes", **overrides: Any) -> RunnerDeployment:
    return decode(RunnerDeployment, {**report_body(name), **overrides})
