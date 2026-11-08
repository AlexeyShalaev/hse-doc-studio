"""Офисные задачи у раннеров из админки: адрес Gotenberg Студии (HSE_STUDIO__RUNNER_INSTALL__OFFICE_URL) раннер получает
в HSE_RUNNER__OFFICE_URL при установке и при обновлении, в Kubernetes и в docker."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import httpx
import pytest
from hse_doc_studio.api.config.runner_install import RunnerInstallConfig
from hse_doc_studio.core.runner_install import InstallStepState, LocalRunnerSpec
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource
from hse_doc_studio.infra.runner_install import docker_host
from hse_doc_studio.infra.runner_install.docker_host import DockerLocalHost
from hse_doc_studio.infra.runner_install.kube_host import KubeLocalHost
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_OFFICE = "http://rel-hse-doc-studio-office-convert:3000"
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


async def _noop(key: str, state: InstallStepState, detail: str) -> None:
    return None


def _env(deployment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    return {e["name"]: e for e in container["env"]}


class _Cluster:
    """Kubernetes API на подмене транспорта: отдаёт живой Deployment, принимает PUT и сразу готовую выкатку."""

    def __init__(self, live: dict[str, Any] | None = None) -> None:
        self.live = live
        self.put: dict[str, Any] | None = None
        self.created: dict[str, Any] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = json.loads(request.content) if request.content else {}
        if request.url.path.endswith("selfsubjectaccessreviews"):
            return httpx.Response(201, json={"status": {"allowed": True}})
        if request.method == "PUT":
            self.put = body
            return httpx.Response(200, json={**body, "metadata": {**body["metadata"], "generation": 3}})
        if request.method == "GET":
            done = {"observedGeneration": 3, "replicas": 1, "updatedReplicas": 1, "availableReplicas": 1}
            item = self.live if self.put is None else {**self.put, "status": done}
            return httpx.Response(200, json={"items": [item] if item is not None else []})
        if request.url.path.endswith("/deployments"):
            self.created = body
        return httpx.Response(201, json=body)


def _kube(cluster: _Cluster | None = None, *, office_url: str = "") -> KubeLocalHost:
    client = KubernetesApiClient(
        "https://k8s.test",
        TokenSource(_TOKEN_FILE),
        Path("/nonexistent-ca.crt"),
        transport=httpx.MockTransport(cluster or _Cluster()),
    )
    return KubeLocalHost(
        enabled=True,
        service_account="rel-hse-doc-studio-runner-ui",
        client=client,
        namespace="studio",
        office_url=office_url,
        rollout_timeout_s=1.0,
        rollout_poll_s=0.01,
    )


def test__kube_manifest__office_url_reaches_the_runner() -> None:
    assert _env(_kube(office_url=_OFFICE).deployment_manifest(_SPEC))["HSE_RUNNER__OFFICE_URL"] == {
        "name": "HSE_RUNNER__OFFICE_URL",
        "value": _OFFICE,
    }


def test__kube_manifest__without_office_url_the_runner_has_no_office() -> None:
    assert "HSE_RUNNER__OFFICE_URL" not in _env(_kube().deployment_manifest(_SPEC))


async def test__kube_install__deployment_carries_the_office_url() -> None:
    cluster = _Cluster()
    await _kube(cluster, office_url=_OFFICE).install(_SPEC, _noop)

    assert cluster.created is not None
    assert _env(cluster.created)["HSE_RUNNER__OFFICE_URL"]["value"] == _OFFICE


async def test__kube_upgrade__existing_runner_without_office_picks_it_up() -> None:
    old = _kube().deployment_manifest(_SPEC)
    old["metadata"]["resourceVersion"] = "77"
    cluster = _Cluster(old)

    await _kube(cluster, office_url=_OFFICE).upgrade(_SPEC.name, "registry.example/hds:1.1.0", _noop)

    assert cluster.put is not None
    assert _env(cluster.put)["HSE_RUNNER__OFFICE_URL"]["value"] == _OFFICE


class _Docker:
    def __init__(self) -> None:
        self.env_file: str | None = None
        self.owned = ""
        self.results: dict[str, tuple[int | None, str, str]] = {}

    async def __call__(self, args: list[str], timeout: float = 30.0) -> tuple[int | None, str, str]:
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


def _inspect(docker: _Docker, *extra: str) -> None:
    docker.owned = "abc"
    env = [
        "HSE_RUNNER__TOKEN=hsrt_topsecret",
        "HSE_RUNNER__API_URL=https://studio.example.org",
        "HSE_RUNNER__DATA_DIR=/var/lib/hse-runner/hse-runner-ab12cd",
        *extra,
    ]
    docker.results["inspect"] = (0, json.dumps([{"Config": {"Image": "registry.example/hds:0.9.0", "Env": env}}]), "")


async def test__docker_install__office_url_goes_to_the_runner_env(docker: _Docker) -> None:
    await DockerLocalHost(office_url=_OFFICE).install(_SPEC, _noop)

    assert docker.env_file is not None
    assert f"HSE_RUNNER__OFFICE_URL={_OFFICE}" in docker.env_file


async def test__docker_install__without_office_url_nothing_is_added(docker: _Docker) -> None:
    await DockerLocalHost().install(_SPEC, _noop)

    assert docker.env_file is not None
    assert "HSE_RUNNER__OFFICE_URL" not in docker.env_file


async def test__docker_upgrade__studio_office_url_replaces_the_old_one(docker: _Docker) -> None:
    _inspect(docker, "HSE_RUNNER__OFFICE_URL=http://old-gotenberg:3000")

    await DockerLocalHost(office_url=_OFFICE).upgrade(_SPEC.name, "registry.example/hds:1.0.0", _noop)

    assert docker.env_file is not None
    assert f"HSE_RUNNER__OFFICE_URL={_OFFICE}" in docker.env_file
    assert "old-gotenberg" not in docker.env_file


async def test__docker_upgrade__without_studio_office_url_the_runner_keeps_its_own(docker: _Docker) -> None:
    _inspect(docker, "HSE_RUNNER__OFFICE_URL=http://own-gotenberg:3000")

    await DockerLocalHost().upgrade(_SPEC.name, "registry.example/hds:1.0.0", _noop)

    assert docker.env_file is not None
    assert "HSE_RUNNER__OFFICE_URL=http://own-gotenberg:3000" in docker.env_file


def test__config__office_url_must_be_http() -> None:
    assert RunnerInstallConfig(office_url=_OFFICE).office_url == _OFFICE
    assert RunnerInstallConfig().office_url == ""
    with pytest.raises(ValidationError):
        RunnerInstallConfig(office_url="gotenberg:3000")
