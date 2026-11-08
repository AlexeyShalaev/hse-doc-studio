"""Поды сборки раннеров из админки в своём namespace (runner.installFromUi.buildNamespace): манифест и обновление."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from hse_doc_studio.core.runner_install import InstallStepState, LocalRunnerSpec
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource
from hse_doc_studio.infra.runner_install.kube_host import KubeLocalHost

pytestmark = pytest.mark.unit

_TOKEN_FILE = Path(tempfile.mkdtemp()) / "token"
_TOKEN_FILE.write_text("sa-token", encoding="utf-8")
_SPEC = LocalRunnerSpec(
    name="hse-runner-ab12cd",
    image="registry.example/hds:1.0.0",
    api_url="http://rel-hse-doc-studio:8000",
    data_dir="/var/lib/hse-runner/hse-runner-ab12cd",
    concurrency=1,
    token="hsrt_topsecret",
)


def _env(deployment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    return {e["name"]: e for e in container["env"]}


class _Cluster:
    """Kubernetes API на подмене транспорта: принимает создание, отдаёт живой Deployment и сразу готовую выкатку."""

    def __init__(self, live: dict[str, Any] | None = None) -> None:
        self.live = live
        self.put: dict[str, Any] | None = None
        self.paths: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.paths.append((request.method, request.url.path))
        if request.url.path.endswith("selfsubjectaccessreviews"):
            return httpx.Response(201, json={"status": {"allowed": True}})
        if request.method == "PUT":
            self.put = body
            return httpx.Response(200, json={**body, "metadata": {**body["metadata"], "generation": 3}})
        if request.method == "GET":
            item = self.live if self.put is None else {**self.put, "status": _done()}
            return httpx.Response(200, json={"items": [item] if item is not None else []})
        return httpx.Response(201, json=body or {})


def _done() -> dict[str, int]:
    return {"observedGeneration": 3, "replicas": 1, "updatedReplicas": 1, "availableReplicas": 1}


def _host(cluster: _Cluster | None = None, *, build_namespace: str | None = None) -> KubeLocalHost:
    transport = httpx.MockTransport(cluster or _Cluster())
    client = KubernetesApiClient(
        "https://k8s.test", TokenSource(_TOKEN_FILE), Path("/nonexistent-ca.crt"), transport=transport
    )
    return KubeLocalHost(
        enabled=True,
        service_account="rel-hse-doc-studio-runner-ui",
        client=client,
        namespace="studio",
        build_namespace=build_namespace,
        rollout_timeout_s=1.0,
        rollout_poll_s=0.01,
    )


def test__manifest__without_build_namespace_builds_stay_with_the_runner() -> None:
    env = _env(_host().deployment_manifest(_SPEC))

    assert env["HSE_RUNNER__K8S__NAMESPACE"]["value"] == "studio"


def test__manifest__build_namespace_reaches_the_runner_and_its_own_pod_stays() -> None:
    deployment = _host(build_namespace="hds-ui-builds").deployment_manifest(_SPEC)
    env = _env(deployment)

    assert env["HSE_RUNNER__K8S__NAMESPACE"]["value"] == "hds-ui-builds"
    # Свой под раннер узнаёт из downward API: он в namespace Студии.
    assert env["HSE_RUNNER__POD__NAMESPACE"]["valueFrom"] == {"fieldRef": {"fieldPath": "metadata.namespace"}}
    assert deployment["spec"]["template"]["spec"]["serviceAccountName"] == "rel-hse-doc-studio-runner-ui"
    assert "namespace" not in deployment["metadata"]


async def test__install__runner_objects_are_created_in_the_studio_namespace() -> None:
    cluster = _Cluster()

    async def report(key: str, state: InstallStepState, detail: str) -> None:
        return None

    await _host(cluster, build_namespace="hds-ui-builds").install(_SPEC, report)

    created = [path for method, path in cluster.paths if method == "POST" and "selfsubject" not in path]
    assert created == [
        "/api/v1/namespaces/studio/secrets",
        "/api/v1/namespaces/studio/persistentvolumeclaims",
        "/apis/apps/v1/namespaces/studio/deployments",
    ]


async def test__upgrade__existing_runner_picks_up_the_build_namespace() -> None:
    old = _host().deployment_manifest(_SPEC)
    old["metadata"]["resourceVersion"] = "77"
    assert _env(old)["HSE_RUNNER__K8S__NAMESPACE"]["value"] == "studio"
    cluster = _Cluster(old)

    async def report(key: str, state: InstallStepState, detail: str) -> None:
        return None

    await _host(cluster, build_namespace="hds-ui-builds").upgrade(_SPEC.name, "registry.example/hds:1.1.0", report)

    assert cluster.put is not None
    assert _env(cluster.put)["HSE_RUNNER__K8S__NAMESPACE"]["value"] == "hds-ui-builds"
    assert ("PUT", "/apis/apps/v1/namespaces/studio/deployments/hse-runner-ab12cd") in cluster.paths


async def test__upgrade__without_build_namespace_nothing_moves() -> None:
    old = _host().deployment_manifest(_SPEC)
    old["metadata"]["resourceVersion"] = "77"
    cluster = _Cluster(old)

    async def report(key: str, state: InstallStepState, detail: str) -> None:
        return None

    await _host(cluster).upgrade(_SPEC.name, "registry.example/hds:1.1.0", report)

    assert cluster.put is not None
    assert _env(cluster.put)["HSE_RUNNER__K8S__NAMESPACE"]["value"] == "studio"
