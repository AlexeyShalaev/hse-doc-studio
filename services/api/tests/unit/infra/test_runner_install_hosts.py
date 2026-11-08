"""Адаптеры установки раннера: docker через `run_docker` и Deployment через Kubernetes API на подмене транспорта."""

from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from hse_doc_studio.core.runner_install import (
    InstallError,
    InstallStepState,
    InvalidResourcesError,
    LocalRunnerSpec,
    ResourceOverrides,
    UnavailableReason,
)
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource
from hse_doc_studio.infra.runner_install import docker_host
from hse_doc_studio.infra.runner_install.docker_host import DockerLocalHost
from hse_doc_studio.infra.runner_install.kube_host import KubeLocalHost, rollout_state

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
    # Свой под из downward API для отчёта в админку: лимиты целыми милликорами и МиБ.
    assert env["HSE_RUNNER__POD__CPU_LIMIT_M"]["valueFrom"]["resourceFieldRef"] == {
        "containerName": "runner",
        "resource": "limits.cpu",
        "divisor": "1m",
    }
    assert env["HSE_RUNNER__POD__SERVICE_ACCOUNT"]["valueFrom"]["fieldRef"] == {"fieldPath": "spec.serviceAccountName"}
    assert bodies["persistentvolumeclaims"]["spec"]["resources"] == {"requests": {"storage": "8Gi"}}  # type: ignore[index]


async def test__kube_install__runner_and_build_pods_get_limits_from_defaults_and_form() -> None:
    cluster = _Cluster()
    spec = replace(_spec(), resources=ResourceOverrides(build_memory="6Gi", runner_cpu="500m"))

    await _kube(cluster).install(spec, _noop)

    bodies = {p.rsplit("/", 1)[-1]: b for m, p, b in cluster.requests if m == "POST"}
    pod = bodies["deployments"]["spec"]["template"]["spec"]  # type: ignore[index]
    container = pod["containers"][0]
    assert container["resources"] == {
        "requests": {"cpu": "100m", "memory": "256Mi", "ephemeral-storage": "128Mi"},
        "limits": {"cpu": "500m", "memory": "2Gi", "ephemeral-storage": "2Gi"},
    }
    env = {e["name"]: e.get("value") for e in container["env"]}
    assert env["HSE_RUNNER__K8S__MEMORY_LIMIT"] == "6Gi"
    assert env["HSE_RUNNER__K8S__MEMORY_REQUEST"] == "1Gi"
    assert env["HSE_RUNNER__K8S__CPU_LIMIT"] == "2"
    assert env["HSE_RUNNER__K8S__EPHEMERAL_STORAGE_LIMIT"] == "4Gi"
    assert pod["automountServiceAccountToken"] is True
    assert next(v for v in pod["volumes"] if v["name"] == "tmp")["emptyDir"] == {"sizeLimit": "1Gi"}


def test__kube_check_resources__out_of_bounds_is_refused() -> None:
    host = KubeLocalHost(enabled=True, service_account="sa")

    host.check_resources(None)
    host.check_resources(ResourceOverrides(build_memory="8Gi"))
    with pytest.raises(InvalidResourcesError):
        host.check_resources(ResourceOverrides(build_memory="128Mi"))
    with pytest.raises(InvalidResourcesError):
        host.check_resources(ResourceOverrides(runner_memory="99Gi"))


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


# ---- обновление на месте ----


async def test__docker_upgrade__keeps_name_token_and_volume_with_the_new_image(docker: _Docker) -> None:
    docker.owned = "abc"
    env = [
        f"HSE_RUNNER__TOKEN={TOKEN}",
        "HSE_RUNNER__API_URL=https://studio.example.org",
        "HSE_RUNNER__DATA_DIR=/var/lib/hse-runner/hse-runner-ab12cd",
        "HSE_RUNNER__CONCURRENCY=3",
        "HSE_RUNNER__NAME=hse-runner-ab12cd",
        "PATH=/usr/bin",
    ]
    docker.results["inspect"] = (0, json.dumps([{"Config": {"Image": "registry.example/hds:0.9.0", "Env": env}}]), "")
    steps: list[tuple[str, InstallStepState]] = []

    async def report(key: str, state: InstallStepState, detail: str) -> None:
        steps.append((key, state))

    outcome = await DockerLocalHost().upgrade("hse-runner-ab12cd", "registry.example/hds:1.0.0", report)

    assert (outcome.old_image, outcome.new_image) == ("registry.example/hds:0.9.0", "registry.example/hds:1.0.0")
    order = [c[0] for c in docker.calls if c[0] in {"pull", "stop", "rm", "run"}]
    # Образ тянется до остановки: простой только на перезапуск.
    assert order == ["pull", "stop", "rm", "run"]
    assert ["stop", "-t", "60", "hse-runner-ab12cd"] in docker.calls
    run = next(c for c in docker.calls if c[0] == "run")
    assert run[run.index("--name") + 1] == "hse-runner-ab12cd"
    assert "/var/lib/hse-runner/hse-runner-ab12cd:/var/lib/hse-runner/hse-runner-ab12cd" in run
    assert run[-3:] == ["registry.example/hds:1.0.0", "hse-doc-studio", "runner"]
    assert TOKEN not in " ".join(" ".join(c) for c in docker.calls)
    assert docker.env_file is not None
    assert f"HSE_RUNNER__TOKEN={TOKEN}" in docker.env_file
    assert "HSE_RUNNER__CONCURRENCY=3" in docker.env_file
    assert "PATH=" not in docker.env_file
    assert steps[-1] == ("recreate", InstallStepState.done)


async def test__docker_upgrade__failed_start_brings_the_previous_image_back(docker: _Docker) -> None:
    docker.owned = "abc"
    env = [f"HSE_RUNNER__TOKEN={TOKEN}", "HSE_RUNNER__DATA_DIR=/var/lib/hse-runner/x1"]
    docker.results["inspect"] = (0, json.dumps([{"Config": {"Image": "img:old", "Env": env}}]), "")
    docker.results["run"] = (125, "", f"bad {TOKEN}")

    with pytest.raises(InstallError) as caught:
        await DockerLocalHost().upgrade("hse-runner-ab12cd", "img:new", _noop)

    runs = [c for c in docker.calls if c[0] == "run"]
    assert [r[-3] for r in runs] == ["img:new", "img:old"]
    assert caught.value.code == "container_start_failed"
    assert TOKEN not in caught.value.detail


async def test__docker_upgrade__foreign_or_missing_container_is_refused(docker: _Docker) -> None:
    with pytest.raises(InstallError) as caught:
        await DockerLocalHost().upgrade("postgres", "img:new", _noop)

    assert caught.value.code == "not_installed"
    assert not [c for c in docker.calls if c[0] in {"pull", "stop", "rm", "run"}]


class _LiveCluster(_Cluster):
    """Кластер с живым Deployment установки: list по имени, PUT и ход выкатки по опросам."""

    def __init__(self, deployment: dict[str, object], *, rollout_after: int = 1) -> None:
        super().__init__()
        self.deployment = deployment
        self.put: dict[str, object] | None = None
        self.rollout_after = rollout_after
        self.polls = 0
        self.update_allowed = True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        if request.url.path.endswith("selfsubjectaccessreviews"):
            verb = body["spec"]["resourceAttributes"]["verb"]  # type: ignore[index]
            return httpx.Response(201, json={"status": {"allowed": verb != "update" or self.update_allowed}})
        if request.method == "PUT":
            self.put = body
            return httpx.Response(200, json={**(body or {}), "metadata": {**body["metadata"], "generation": 7}})  # type: ignore[index]
        if request.method == "GET":
            if self.put is None:
                return httpx.Response(200, json={"items": [self.deployment]})
            self.polls += 1
            done = self.polls >= self.rollout_after
            status = {
                "observedGeneration": 7,
                "replicas": 1,
                "updatedReplicas": 1 if done else 0,
                "availableReplicas": 1 if done else 0,
            }
            return httpx.Response(200, json={"items": [{**self.put, "status": status}]})
        return httpx.Response(200, json={})


def _installed(host: KubeLocalHost, spec: LocalRunnerSpec) -> dict[str, object]:
    """Deployment, каким его создала установка, плюс то, что дописывает кластер."""
    deployment = host.deployment_manifest(spec)
    deployment["metadata"]["resourceVersion"] = "4242"
    return deployment


def _upgrading(cluster: _LiveCluster) -> KubeLocalHost:
    client = KubernetesApiClient(
        "https://k8s.test",
        TokenSource(_TOKEN_FILE),
        Path("/nonexistent-ca.crt"),
        transport=httpx.MockTransport(cluster),
    )
    return KubeLocalHost(
        enabled=True,
        service_account="rel-runner-ui",
        client=client,
        namespace="studio",
        rollout_timeout_s=1.0,
        rollout_poll_s=0.01,
    )


def _container(deployment: dict[str, object]) -> dict[str, object]:
    return deployment["spec"]["template"]["spec"]["containers"][0]  # type: ignore[index, no-any-return]


async def test__kube_upgrade__new_image_keeps_overrides_token_volume_and_address() -> None:
    spec = replace(
        _spec(),
        image="registry.example/hds:0.9.0",
        api_url="http://rel-hse-doc-studio:8000",
        resources=ResourceOverrides(build_memory="6Gi", runner_cpu="500m"),
    )
    cluster = _LiveCluster(_installed(_upgrading(_LiveCluster({})), spec))
    steps: list[tuple[str, InstallStepState]] = []

    async def report(key: str, state: InstallStepState, detail: str) -> None:
        steps.append((key, state))

    outcome = await _upgrading(cluster).upgrade("hse-runner-ab12cd", "registry.example/hds:1.0.0", report)

    assert outcome.old_image == "registry.example/hds:0.9.0"
    put = cluster.put
    assert put is not None
    # Замена целиком с версией живого объекта; Secret и том не создаются и не меняются.
    assert put["metadata"]["resourceVersion"] == "4242"  # type: ignore[index]
    changed = [(m, path) for m, path, _ in cluster.requests if m in {"POST", "DELETE"}]
    assert [path for _, path in changed if not path.endswith("selfsubjectaccessreviews")] == []
    container = _container(put)
    assert container["image"] == "registry.example/hds:1.0.0"
    env = {e["name"]: e for e in container["env"]}  # type: ignore[attr-defined]
    assert env["HSE_RUNNER__TOKEN"]["valueFrom"]["secretKeyRef"] == {"name": "hse-runner-ab12cd-token", "key": "token"}
    assert env["HSE_RUNNER__API_URL"]["value"] == "http://rel-hse-doc-studio:8000"
    assert env["HSE_RUNNER__DATA_DIR"]["value"] == "/var/lib/hse-runner/hse-runner-ab12cd"
    assert env["HSE_RUNNER__CONCURRENCY"]["value"] == "2"
    assert env["HSE_RUNNER__K8S__MEMORY_LIMIT"]["value"] == "6Gi"
    assert container["resources"]["limits"]["cpu"] == "500m"  # type: ignore[index]
    volumes = put["spec"]["template"]["spec"]["volumes"]  # type: ignore[index]
    assert {"name": "runner-data", "persistentVolumeClaim": {"claimName": "hse-runner-ab12cd-data"}} in volumes
    assert put["spec"]["strategy"] == {"type": "Recreate"}  # type: ignore[index]
    # Под пересоздаётся, даже если манифест не изменился.
    assert "hse-doc-studio/restarted-at" in put["spec"]["template"]["metadata"]["annotations"]  # type: ignore[index]
    assert json.loads(put["metadata"]["annotations"]["hse-doc-studio/runner-resources"]) == {  # type: ignore[index]
        "build_memory": "6Gi",
        "runner_cpu": "500m",
    }
    assert TOKEN not in json.dumps(put)
    assert [k for k, s in steps if s is InstallStepState.done] == ["image", "manifest", "rollout"]


async def test__kube_upgrade__old_install_without_annotation_keeps_its_live_limits() -> None:
    deployment = _installed(_upgrading(_LiveCluster({})), replace(_spec(), resources=ResourceOverrides(build_cpu="3")))
    del deployment["metadata"]["annotations"]  # type: ignore[attr-defined]
    container = _container(deployment)
    container["resources"]["limits"]["memory"] = "3Gi"  # type: ignore[index]
    cluster = _LiveCluster(deployment)

    await _upgrading(cluster).upgrade("hse-runner-ab12cd", "img:new", _noop)

    assert cluster.put is not None
    put = _container(cluster.put)
    env = {e["name"]: e.get("value") for e in put["env"]}  # type: ignore[attr-defined]
    assert env["HSE_RUNNER__K8S__CPU_LIMIT"] == "3"
    assert put["resources"]["limits"]["memory"] == "3Gi"  # type: ignore[index]
    # Совпадающие с умолчанием значения переопределением не считаются.
    assert json.loads(cluster.put["metadata"]["annotations"]["hse-doc-studio/runner-resources"]) == {  # type: ignore[index]
        "build_cpu": "3",
        "runner_memory": "3Gi",
    }


async def test__kube_upgrade__limit_beyond_the_current_bounds_falls_back_to_the_default() -> None:
    deployment = _installed(_upgrading(_LiveCluster({})), _spec())
    deployment["metadata"]["annotations"] = {  # type: ignore[index]
        "hse-doc-studio/runner-resources": json.dumps({"build_memory": "64Gi", "build_cpu": "3"})
    }
    cluster = _LiveCluster(deployment)
    details: dict[str, str] = {}

    async def report(key: str, state: InstallStepState, detail: str) -> None:
        if state is InstallStepState.done:
            details[key] = detail

    await _upgrading(cluster).upgrade("hse-runner-ab12cd", "img:new", report)

    assert cluster.put is not None
    env = {e["name"]: e.get("value") for e in _container(cluster.put)["env"]}  # type: ignore[attr-defined]
    assert (env["HSE_RUNNER__K8S__MEMORY_LIMIT"], env["HSE_RUNNER__K8S__CPU_LIMIT"]) == ("4Gi", "3")
    assert details["manifest"] == "build_memory"


async def test__kube_upgrade__waits_for_the_rollout() -> None:
    cluster = _LiveCluster(_installed(_upgrading(_LiveCluster({})), _spec()), rollout_after=3)

    await _upgrading(cluster).upgrade("hse-runner-ab12cd", "img:new", _noop)

    assert cluster.polls == 3


async def test__kube_upgrade__rollout_that_never_finishes_is_a_timeout() -> None:
    cluster = _LiveCluster(_installed(_upgrading(_LiveCluster({})), _spec()), rollout_after=10_000)

    with pytest.raises(InstallError) as caught:
        await _upgrading(cluster).upgrade("hse-runner-ab12cd", "img:new", _noop)

    assert caught.value.code == "rollout_timeout"


async def test__kube_upgrade__without_update_right_nothing_is_changed() -> None:
    cluster = _LiveCluster(_installed(_upgrading(_LiveCluster({})), _spec()))
    cluster.update_allowed = False

    with pytest.raises(InstallError) as caught:
        await _upgrading(cluster).upgrade("hse-runner-ab12cd", "img:new", _noop)

    assert caught.value.code == "kube_forbidden"
    assert cluster.put is None


async def test__kube_upgrade__unknown_deployment_is_not_installed() -> None:
    cluster = _Cluster()

    with pytest.raises(InstallError) as caught:
        await _kube(cluster).upgrade("hse-runner-zz", "img:new", _noop)

    assert caught.value.code == "not_installed"
    assert not [m for m, _, _ in cluster.requests if m == "PUT"]


def test__rollout_state__reads_like_kubectl_rollout_status() -> None:
    def item(**status: object) -> dict[str, object]:
        return {"metadata": {"generation": 2}, "spec": {"replicas": 1}, "status": status}

    done = {"observedGeneration": 2, "replicas": 1, "updatedReplicas": 1, "availableReplicas": 1}
    assert rollout_state(item(**done), 2) == "done"
    assert rollout_state(item(**{**done, "observedGeneration": 1}), 2) == "pending"
    assert rollout_state(item(**{**done, "replicas": 2}), 2) == "pending"
    assert rollout_state(item(**{**done, "availableReplicas": 0}), 2) == "pending"
    stuck = {**done, "availableReplicas": 0, "conditions": [{"reason": "ProgressDeadlineExceeded"}]}
    assert rollout_state(item(**stuck), 2) == "failed"
    # Условие от прошлой выкатки до нового поколения не в счёт.
    assert rollout_state(item(**{**stuck, "observedGeneration": 1}), 2) == "pending"
