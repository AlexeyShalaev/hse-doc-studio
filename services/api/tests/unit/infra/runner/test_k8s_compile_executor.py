"""Раннер с executor=kubernetes: сборка подом через тот же CompileJobExecutor, коды сбоев, настройки из окружения."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from hse_doc_studio.core.compile.failure import failure_message
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.entities import compile_payload_of
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.jobs.wire import JobEnvelope
from hse_doc_studio.infra.compile.backend import BuildBackend
from hse_doc_studio.infra.compile.k8s.api import KubeApiError, PodState
from hse_doc_studio.infra.di.containers.runner import create_runner_container
from hse_doc_studio.infra.jobs.embedded_runner import EmbeddedCompileRunner
from hse_doc_studio.infra.runner.compile_executor import CompileJobExecutor
from hse_doc_studio.infra.runner.config import BuildExecutorKind, RunnerConfig
from hse_doc_studio.infra.runner.executor import JobContext
from hse_doc_studio.infra.runner.workspace import BlobCache, RunnerWorkspaces

from tests.unit.core.jobs.samples import make_compile_spec
from tests.unit.infra.compile.k8s.fake_kube import FakeKubeApi, FakePod

_SOURCE = b"\\documentclass{article}"


class _Fetcher:
    @contextlib.contextmanager
    def bind(self, job_id: str, job_token: str) -> Iterator[None]:
        yield

    async def __call__(self, sha256: str) -> bytes:
        return _SOURCE


def _config(tmp_path: Path) -> RunnerConfig:
    return RunnerConfig(
        api_url="http://api",
        token="t",
        data_dir=tmp_path / "runner",
        executor=BuildExecutorKind.kubernetes,
        k8s={"namespace": "builds", "owner_pod_uid": "uid-1"},
    )


async def _executor(tmp_path: Path, api: FakeKubeApi) -> CompileJobExecutor:
    config = _config(tmp_path)
    container = create_runner_container(config, kube_api=api)
    runner = await container.get(EmbeddedCompileRunner)
    fetcher = _Fetcher()
    cache = BlobCache(config.data_dir, fetcher)
    return CompileJobExecutor(
        workspaces=RunnerWorkspaces(config.data_dir, cache),
        cache=cache,
        fetcher=fetcher,  # type: ignore[arg-type]
        runner=runner,
        cache_max_bytes=1 << 20,
    )


def _envelope() -> JobEnvelope:
    spec = make_compile_spec()
    payload = replace(compile_payload_of(spec), default_passes=7)
    manifest = (ManifestFile("tz/main.tex", hashlib.sha256(_SOURCE).hexdigest(), len(_SOURCE)),)
    return JobEnvelope(replace(spec, payload=payload), manifest, 600.0, 1, "token")


def _ctx(lines: list[str]) -> JobContext:
    return JobContext(log=lines.append, cancelled=asyncio.Event())


async def test__execute__kubernetes__builds_in_pod_and_returns_the_pdf(tmp_path: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster")
    lines: list[str] = []

    outcome = await (await _executor(tmp_path, api)).execute(_envelope(), _ctx(lines))

    assert outcome.result.status is JobStatus.succeeded
    assert outcome.result.data.pages == 3  # type: ignore[union-attr]
    assert outcome.result.data.words == 6  # type: ignore[union-attr]
    assert [o.ref.path for o in outcome.outputs] == ["tz/main.pdf"]
    assert outcome.outputs[0].path.read_bytes() == b"%PDF-1.5 built"
    assert any("latexmk ok" in line for line in lines)
    pod = api.only_pod()
    assert pod.labels["hse-doc-studio/runner"] == "uid-1"
    assert (pod.work / "tz" / "main.tex").read_bytes() == _SOURCE
    assert api.deleted == [pod.name]


async def test__execute__kubernetes_image_missing__typed_failure(tmp_path: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster", states=[PodState(phase="Pending", waiting_reason="ImagePullBackOff")])

    with pytest.raises(JobFailure) as caught:
        await (await _executor(tmp_path, api)).execute(_envelope(), _ctx([]))

    assert caught.value.error.code == "image_missing"
    assert caught.value.error.detail == "texlive/texlive:TL2024-historic"


async def test__execute__kubernetes_forbidden__build_backend_unavailable(tmp_path: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster", create_error=KubeApiError("pods is forbidden", status=403))

    with pytest.raises(JobFailure) as caught:
        await (await _executor(tmp_path, api)).execute(_envelope(), _ctx([]))

    assert caught.value.error.code == "build_backend_unavailable"
    assert "forbidden" in (caught.value.error.detail or "")


async def test__execute__kubernetes_oom__out_of_memory_code_with_user_text(tmp_path: Path) -> None:
    async def cut(pod: FakePod) -> list[str]:
        return ["This is XeTeX"]

    api = FakeKubeApi(
        tmp_path / "cluster",
        build=cut,
        hang_after_log=False,
        after_log_state=PodState(phase="Failed", terminated_reason="OOMKilled", terminated_exit_code=137),
    )

    with pytest.raises(JobFailure) as caught:
        await (await _executor(tmp_path, api)).execute(_envelope(), _ctx([]))

    assert caught.value.error.code == "build_out_of_memory"
    assert "OOMKilled" in (caught.value.error.detail or "")
    assert "памяти" in failure_message("build_out_of_memory", Lang.ru)
    assert "out of memory" in failure_message("build_out_of_memory", Lang.en)
    assert failure_message("build_storage_exceeded", Lang.en) != failure_message("unknown_code_xyz", Lang.en)


async def test__backend__kubernetes__tex_without_docker_and_sweep_by_instance(tmp_path: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster")
    api.extra = {"hds-build-old": {"hse-doc-studio/component": "build", "hse-doc-studio/runner": "uid-1"}}
    container = create_runner_container(_config(tmp_path), kube_api=api)

    backend = await container.get(BuildBackend)

    assert backend.name == "kubernetes"
    assert backend.tex_available is True
    assert await backend.sweep() == 1
    assert api.deleted == ["hds-build-old"]
    await container.close()


def test__config__env__executor_and_nested_k8s_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HSE_RUNNER__API_URL", "http://api")
    monkeypatch.setenv("HSE_RUNNER__EXECUTOR", "kubernetes")
    monkeypatch.setenv("HSE_RUNNER__K8S__NAMESPACE", "builds")
    monkeypatch.setenv("HSE_RUNNER__K8S__NODE_SELECTOR", '{"pool": "tex"}')
    monkeypatch.setenv("HSE_RUNNER__K8S__TOLERATIONS", '[{"key": "tex", "operator": "Exists"}]')
    monkeypatch.setenv("HSE_RUNNER__K8S__ACTIVE_DEADLINE_S", "900")

    config = RunnerConfig()

    assert config.executor is BuildExecutorKind.kubernetes
    assert config.k8s.namespace == "builds"
    assert config.k8s.node_selector == {"pool": "tex"}
    assert config.k8s.tolerations == [{"key": "tex", "operator": "Exists"}]
    assert config.k8s.active_deadline_s == 900


def test__config__default__docker_for_compatibility() -> None:
    assert RunnerConfig(api_url="http://api").executor is BuildExecutorKind.docker
