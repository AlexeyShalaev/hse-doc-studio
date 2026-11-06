"""Адаптеры установки раннера: docker через `run_docker` и Deployment через Kubernetes API на подмене транспорта."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import httpx
import pytest
from hse_doc_studio.core.runner_install import (
    InstallError,
    InstallStepState,
    LocalRunnerSpec,
    UnavailableReason,
)
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource
from hse_doc_studio.infra.runner_install import docker_host
from hse_doc_studio.infra.runner_install.docker_host import DockerLocalHost
from hse_doc_studio.infra.runner_install.kube_host import KubeLocalHost

pytestmark = pytest.mark.unit

TOKEN = "hsrt_topsecret"
_TOKEN_FILE = Path(tempfile.mkdtemp()) / "token"
_TOKEN_FILE.write_text("sa-token", encoding="utf-8")


def _spec(name: str = "hse-runner-ab12cd") -> LocalRunnerSpec:
    return LocalRunnerSpec(
        name=name,
        image="registry.example/hds:1.0.0",
        api_url="https://studio.example.org",
        data_dir=f"/var/lib/hse-runner/{name}",
        concurrency=2,
        token=TOKEN,
    )


class _Docker:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.env_file: str | None = None
        self.owned = ""
        self.results: dict[str, tuple[int | None, str, str]] = {}

    async def __call__(self, args: list[str], timeout: float = 30.0) -> tuple[int | None, str, str]:
        self.calls.append(args)
        if args[0] == "run" and "--env-file" in args:
            self.env_file = Path(args[args.index("--env-file") + 1]).read_text(encoding="utf-8")
        if args[0] == "ps" and "-q" in args:
            return 0, self.owned, ""
        return self.results.get(args[0], (0, "", ""))


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> _Docker:
    fake = _Docker()
    monkeypatch.setattr(docker_host, "run_docker", fake)
    return fake


async def _noop(key: str, state: InstallStepState, detail: str) -> None:
    return None


async def test__docker_capability__reasons(monkeypatch: pytest.MonkeyPatch) -> None:
    async def down(timeout: float = 5.0) -> bool:
        return False

    async def up(timeout: float = 5.0) -> bool:
        return True

    monkeypatch.setattr(docker_host, "docker_available", down)
    monkeypatch.setattr(docker_host, "_socket_present", lambda: False)
    assert (await DockerLocalHost().capability()).reason is UnavailableReason.no_socket
    monkeypatch.setattr(docker_host, "_socket_present", lambda: True)
    assert (await DockerLocalHost().capability()).reason is UnavailableReason.docker_unreachable
    assert (await DockerLocalHost(enabled=False).capability()).reason is UnavailableReason.disabled
    monkeypatch.setattr(docker_host, "docker_available", up)
    assert (await DockerLocalHost().capability()).available


async def test__docker_install__token_goes_through_env_file_not_arguments(docker: _Docker) -> None:
    await DockerLocalHost().install(_spec(), _noop)

    run = next(c for c in docker.calls if c[0] == "run")
    assert TOKEN not in " ".join(" ".join(c) for c in docker.calls)
    assert docker.env_file is not None
    assert f"HSE_RUNNER__TOKEN={TOKEN}" in docker.env_file
    assert "HSE_RUNNER__API_URL=https://studio.example.org" in docker.env_file
    assert "--restart" in run
    assert "unless-stopped" in run
    assert "hse-doc-studio.runner-install=true" in run
    mount = "/var/lib/hse-runner/hse-runner-ab12cd:/var/lib/hse-runner/hse-runner-ab12cd"
    assert mount in run
    assert run[-3:] == ["registry.example/hds:1.0.0", "hse-doc-studio", "runner"]


async def test__docker_install__env_file_is_removed_afterwards(docker: _Docker) -> None:
    await DockerLocalHost().install(_spec(), _noop)

    run = next(c for c in docker.calls if c[0] == "run")
    assert not Path(run[run.index("--env-file") + 1]).exists()


async def test__docker_install__pull_failure_is_reported_without_secret(docker: _Docker) -> None:
    docker.results["pull"] = (1, "", f"denied for {TOKEN}")

    with pytest.raises(InstallError) as caught:
        await DockerLocalHost().install(_spec(), _noop)

    assert caught.value.code == "image_pull_failed"
    assert TOKEN not in caught.value.detail
    assert not [c for c in docker.calls if c[0] == "run"]


async def test__docker_install__start_failure_is_reported(docker: _Docker) -> None:
    docker.results["run"] = (125, "", "port is already allocated")

    with pytest.raises(InstallError) as caught:
        await DockerLocalHost().install(_spec(), _noop)

    assert caught.value.code == "container_start_failed"


async def test__docker_install__replaces_only_its_own_container(docker: _Docker) -> None:
    await DockerLocalHost().install(_spec(), _noop)
    assert not [c for c in docker.calls if c[0] == "rm"]

    docker.owned = "abc"
    await DockerLocalHost().install(_spec(), _noop)
    assert ["rm", "-f", "hse-runner-ab12cd"] in docker.calls


async def test__docker__bad_names_never_reach_docker(docker: _Docker) -> None:
    with pytest.raises(InstallError):
        await DockerLocalHost().install(_spec("x; rm -rf /"), _noop)

    assert await DockerLocalHost().remove("../etc") is False
    assert docker.calls == []


async def test__docker_remove__refuses_foreign_containers(docker: _Docker) -> None:
    assert await DockerLocalHost().remove("postgres") is False
    assert ["rm", "-f", "postgres"] not in docker.calls

    docker.owned = "abc"
    assert await DockerLocalHost().remove("hse-runner-ab12cd") is True


async def test__docker_list__parses_json_rows(docker: _Docker) -> None:
    row = {"Names": "hse-runner-1", "Image": "img:1", "State": "running", "CreatedAt": "2026-11-06 12:00:00 +0000 UTC"}
    docker.results["ps"] = (0, json.dumps(row) + "\nnot json\n", "")

    found = await DockerLocalHost().list_instances()

    assert [(i.name, i.state) for i in found] == [("hse-runner-1", "running")]
    assert found[0].created_at is not None


class _Cluster:
    """Минимальный Kubernetes API: хранит созданное, умеет отказать в правах и вернуть конфликт."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, object] | None]] = []
        self.allowed = True
        self.conflicts: set[str] = set()
        self.items: list[dict[str, object]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        path = request.url.path
        if path.endswith("selfsubjectaccessreviews"):
            return httpx.Response(201, json={"status": {"allowed": self.allowed}})
        if request.method == "POST":
            kind = path.rsplit("/", 1)[-1]
            if kind in self.conflicts:
                self.conflicts.discard(kind)
                return httpx.Response(409, json={"message": "exists"})
            return httpx.Response(201, json=body or {})
        if request.method == "GET":
            return httpx.Response(200, json={"items": self.items})
        return httpx.Response(200, json={})


def _kube(cluster: _Cluster, *, enabled: bool = True) -> KubeLocalHost:
    token_file = _TOKEN_FILE
    client = KubernetesApiClient(
        "https://k8s.test", TokenSource(token_file), Path("/nonexistent-ca.crt"), transport=httpx.MockTransport(cluster)
    )
    return KubeLocalHost(
        enabled=enabled, service_account="rel-runner-ui", storage_size="8Gi", client=client, namespace="studio"
    )


async def test__kube_capability__reasons() -> None:
    cluster = _Cluster()
    assert (await _kube(cluster, enabled=False).capability()).reason is UnavailableReason.disabled
    assert (await _kube(cluster).capability()).available
    cluster.allowed = False
    assert (await _kube(cluster).capability()).reason is UnavailableReason.no_permission


async def test__kube_capability__outside_a_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    host = KubeLocalHost(enabled=True, service_account="sa")

    assert (await host.capability()).reason is UnavailableReason.not_in_cluster


async def test__kube_install__creates_secret_volume_deployment_in_order() -> None:
    cluster = _Cluster()
    steps: list[tuple[str, InstallStepState]] = []

    async def report(key: str, state: InstallStepState, detail: str) -> None:
        steps.append((key, state))

    await _kube(cluster).install(_spec(), report)

    created = [(p.rsplit("/", 1)[-1]) for m, p, _ in cluster.requests if m == "POST"]
    assert created == ["secrets", "persistentvolumeclaims", "deployments"]
    assert steps == [
        ("secret", InstallStepState.running),
        ("secret", InstallStepState.done),
        ("volume", InstallStepState.running),
        ("volume", InstallStepState.done),
        ("deployment", InstallStepState.running),
        ("deployment", InstallStepState.done),
    ]


async def test__kube_install__token_lives_only_in_the_secret_and_pod_is_restricted() -> None:
    cluster = _Cluster()

    await _kube(cluster).install(_spec(), _noop)

    bodies = {p.rsplit("/", 1)[-1]: b for m, p, b in cluster.requests if m == "POST"}
    assert bodies["secrets"]["stringData"] == {"token": TOKEN}  # type: ignore[index]
    deployment = json.dumps(bodies["deployments"])
    assert TOKEN not in deployment
    pod = bodies["deployments"]["spec"]["template"]["spec"]  # type: ignore[index]
    assert pod["serviceAccountName"] == "rel-runner-ui"
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    container = pod["containers"][0]
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["capabilities"] == {"drop": ["ALL"]}
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    env = {e["name"]: e for e in container["env"]}
    assert env["HSE_RUNNER__TOKEN"]["valueFrom"]["secretKeyRef"] == {"name": "hse-runner-ab12cd-token", "key": "token"}
    assert env["HSE_RUNNER__EXECUTOR"]["value"] == "kubernetes"
    assert env["HSE_RUNNER__K8S__NAMESPACE"]["value"] == "studio"
    assert bodies["persistentvolumeclaims"]["spec"]["resources"] == {"requests": {"storage": "8Gi"}}  # type: ignore[index]


async def test__kube_install__reinstall_replaces_secret_and_deployment_but_keeps_the_volume() -> None:
    cluster = _Cluster()
    cluster.conflicts = {"secrets", "persistentvolumeclaims", "deployments"}

    await _kube(cluster).install(_spec(), _noop)

    deleted = [p.rsplit("/", 1)[-1] for m, p, _ in cluster.requests if m == "DELETE"]
    assert deleted == ["hse-runner-ab12cd-token", "hse-runner-ab12cd"]


async def test__kube_install__forbidden_is_a_clear_error_without_secret() -> None:
    def deny(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": f"forbidden {TOKEN}"})

    token_file = _TOKEN_FILE
    client = KubernetesApiClient(
        "https://k8s.test", TokenSource(token_file), Path("/nonexistent-ca.crt"), transport=httpx.MockTransport(deny)
    )
    host = KubeLocalHost(enabled=True, service_account="sa", client=client, namespace="studio")

    with pytest.raises(InstallError) as caught:
        await host.install(_spec(), _noop)

    assert caught.value.code == "kube_forbidden"
    assert TOKEN not in caught.value.detail


async def test__kube_install__bad_name_is_refused_before_any_call() -> None:
    cluster = _Cluster()

    with pytest.raises(InstallError):
        await _kube(cluster).install(_spec("Bad_Name"), _noop)

    assert cluster.requests == []


async def test__kube_remove__only_installed_runners() -> None:
    cluster = _Cluster()
    cluster.items = [
        {
            "metadata": {"name": "hse-runner-ab12cd", "creationTimestamp": "2026-11-06T12:00:00Z"},
            "spec": {"template": {"spec": {"containers": [{"image": "img:1"}]}}},
            "status": {"readyReplicas": 1},
        }
    ]
    host = _kube(cluster)

    assert await host.remove("other-deployment") is False
    assert await host.remove("hse-runner-ab12cd") is True
    deleted = [p.rsplit("/", 1)[-1] for m, p, _ in cluster.requests if m == "DELETE"]
    assert deleted == ["hse-runner-ab12cd", "hse-runner-ab12cd-token", "hse-runner-ab12cd-data"]
    listed = await host.list_instances()
    assert [(i.name, i.state) for i in listed] == [("hse-runner-ab12cd", "running")]
