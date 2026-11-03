"""`KubeCluster`: синхронный порт апдейтера поверх асинхронного клиента, пути и права ровно те, что в Role чарта."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource
from hse_doc_studio.infra.update.server_updater.kube import MERGE, KubeCluster


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


@pytest.fixture
def cluster(tmp_path: Path, seen: list[httpx.Request]) -> Iterator[KubeCluster]:
    token = tmp_path / "token"
    token.write_text("t", encoding="utf-8")

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/pods/p/log"):
            return httpx.Response(200, text="log line")
        if request.url.path.endswith("/jobs/missing"):
            return httpx.Response(404, json={"reason": "NotFound"})
        if request.method == "GET" and request.url.path.endswith(("/pods", "/jobs")):
            return httpx.Response(200, json={"items": [{"metadata": {"name": "a"}}]})
        return httpx.Response(200, json={"metadata": {"name": "x"}})

    client = KubernetesApiClient(
        "https://k8s.local", TokenSource(token), tmp_path / "ca", transport=httpx.MockTransport(handle)
    )
    kube = KubeCluster(client, namespace="studio", deployment="rel-api")
    yield kube
    kube.close()


def test__paths_stay_inside_the_namespace_and_the_one_deployment(
    cluster: KubeCluster, seen: list[httpx.Request]
) -> None:
    cluster.get_deployment()
    cluster.patch_deployment({"spec": {"replicas": 0}})
    cluster.patch_deployment({"metadata": {"annotations": {"k": None}}}, content_type=MERGE)
    cluster.create_job({"metadata": {"name": "j"}})
    assert cluster.get_job("missing") is None
    assert cluster.list_jobs("a=b") == [{"metadata": {"name": "a"}}]
    cluster.delete_job("j")
    assert cluster.list_pods("job-name=j") == [{"metadata": {"name": "a"}}]
    assert cluster.pod_log("p", "migrate") == "log line"

    calls = [(r.method, r.url.path) for r in seen]
    assert calls == [
        ("GET", "/apis/apps/v1/namespaces/studio/deployments/rel-api"),
        ("PATCH", "/apis/apps/v1/namespaces/studio/deployments/rel-api"),
        ("PATCH", "/apis/apps/v1/namespaces/studio/deployments/rel-api"),
        ("POST", "/apis/batch/v1/namespaces/studio/jobs"),
        ("GET", "/apis/batch/v1/namespaces/studio/jobs/missing"),
        ("GET", "/apis/batch/v1/namespaces/studio/jobs"),
        ("DELETE", "/apis/batch/v1/namespaces/studio/jobs/j"),
        ("GET", "/api/v1/namespaces/studio/pods"),
        ("GET", "/api/v1/namespaces/studio/pods/p/log"),
    ]
    assert seen[1].headers["content-type"] == "application/strategic-merge-patch+json"
    assert seen[2].headers["content-type"] == "application/merge-patch+json"
    assert json.loads(seen[2].content) == {"metadata": {"annotations": {"k": None}}}
    assert seen[6].url.params["propagationPolicy"] == "Background"


def test__forbidden_is_raised_with_the_status(tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("t", encoding="utf-8")
    client = KubernetesApiClient(
        "https://k8s.local",
        TokenSource(token),
        tmp_path / "ca",
        transport=httpx.MockTransport(lambda _r: httpx.Response(403, json={"message": "forbidden"})),
    )
    kube = KubeCluster(client, namespace="studio", deployment="rel-api")
    try:
        with pytest.raises(KubeApiError) as caught:
            kube.get_deployment()
        assert caught.value.status == 403
    finally:
        kube.close()
