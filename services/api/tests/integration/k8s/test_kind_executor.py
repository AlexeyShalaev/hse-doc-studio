"""Исполнитель kubernetes на настоящем кластере (kind): права из чарта, Pod Security restricted, exec и лог.

Нужны HSE_TEST_K8S_API_URL, HSE_TEST_K8S_TOKEN_FILE (токен ServiceAccount раннера из чарта), HSE_TEST_K8S_CA_FILE,
HSE_TEST_K8S_NAMESPACE (namespace подов сборки) и HSE_TEST_K8S_IMAGE (образ из tests/integration/k8s/fake-tex).
Подготовку делает джоба CI `k8s-runner-kind`, вручную см. docs/design/k8s-runner.md, раздел 9.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from hse_doc_studio.core.compile.errors import ImageMissingError
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource
from hse_doc_studio.infra.compile.k8s.config import KubernetesExecutorConfig
from hse_doc_studio.infra.compile.k8s.executor import KubernetesTexExecutor
from hse_doc_studio.infra.compile.k8s.pod import build_selector
from hse_doc_studio.infra.compile.latexmk import SENTINEL_DONE, SENTINEL_FAILED, SENTINEL_PAGES, SENTINEL_WORDS

_ENV = ("HSE_TEST_K8S_API_URL", "HSE_TEST_K8S_TOKEN_FILE", "HSE_TEST_K8S_CA_FILE", "HSE_TEST_K8S_NAMESPACE")

pytestmark = [
    pytest.mark.k8s,
    pytest.mark.timeout(300),
    pytest.mark.skipif(not all(os.environ.get(name) for name in (*_ENV, "HSE_TEST_K8S_IMAGE")), reason="нет кластера"),
]


@pytest.fixture
async def api() -> AsyncIterator[KubernetesApiClient]:
    client = KubernetesApiClient(
        os.environ["HSE_TEST_K8S_API_URL"],
        TokenSource(Path(os.environ["HSE_TEST_K8S_TOKEN_FILE"])),
        Path(os.environ["HSE_TEST_K8S_CA_FILE"]),
    )
    yield client
    await client.aclose()


def _executor(  # noqa: PLR0913
    api: KubernetesApiClient,
    *,
    image: str | None = None,
    idle: float = 60.0,
    instance: str | None = None,
    probe: float = 30.0,
    counts_timeout: float = 120.0,
) -> KubernetesTexExecutor:
    config = KubernetesExecutorConfig(
        namespace=os.environ["HSE_TEST_K8S_NAMESPACE"],
        image=image or os.environ["HSE_TEST_K8S_IMAGE"],
        image_pull_policy="IfNotPresent",
        pod_start_timeout_s=120,
        cpu_request="50m",
        memory_request="32Mi",
        cpu_limit="500m",
        memory_limit="128Mi",
    )
    return KubernetesTexExecutor(
        api,
        config,
        image="unused",
        instance=instance or f"it-{uuid.uuid4().hex[:8]}",
        idle_timeout_s=idle,
        probe_s=probe,
        counts_timeout_s=counts_timeout,
    )


def _project(tmp_path: Path, body: str) -> Path:
    root = tmp_path / "project"
    (root / "tz").mkdir(parents=True)
    (root / "tz" / "main.tex").write_text(body, encoding="utf-8")
    (root / "common").mkdir()
    (root / "common" / "meta.tex").write_text("meta", encoding="utf-8")
    return root


async def _collect(executor: KubernetesTexExecutor, project: Path, lines: list[str] | None = None) -> list[str]:
    out = lines if lines is not None else []
    stream = await executor.run(project, "tz/main.tex", "xelatex", 5, "tz", uuid.uuid4())
    async for line in stream:
        out.append(line)
    return out


async def test__kind__build__pdf_counts_and_pod_removed(api: KubernetesApiClient, tmp_path: Path) -> None:
    executor = _executor(api)
    project = _project(tmp_path, "\\documentclass{article}")

    lines = await _collect(executor, project)

    assert lines[-1] == SENTINEL_DONE, lines
    assert f"{SENTINEL_PAGES}2" in lines
    assert f"{SENTINEL_WORDS}8:45" in lines
    assert any("fake build of main.tex in /work/tz" in line for line in lines)
    assert (project / "tz" / "main.pdf").read_bytes() == b"%PDF-1.5 fake main\n"
    assert await executor.sweep() == 0


async def test__kind__texcount_parse_errors__build_finishes(api: KubernetesApiClient, tmp_path: Path) -> None:
    # Регрессия 0.14.0: вывод texcount без перевода строки в конце склеивал маркер конца со счётчиками,
    # и готовая сборка падала через idle_timeout.
    project = _project(tmp_path, "texerr")

    lines = await _collect(_executor(api, idle=20, probe=5), project)

    assert lines[-1] == SENTINEL_DONE, lines
    assert f"{SENTINEL_WORDS}8:45" in lines


async def test__kind__texcount_hangs__pdf_without_counts(api: KubernetesApiClient, tmp_path: Path) -> None:
    project = _project(tmp_path, "slowcount")

    lines = await _collect(_executor(api, idle=60, probe=1, counts_timeout=5), project)

    assert lines[-1] == SENTINEL_DONE, lines
    assert not any(line.startswith(SENTINEL_WORDS) for line in lines)
    assert (project / "tz" / "main.pdf").read_bytes() == b"%PDF-1.5 fake main\n"


async def test__kind__latexmk_fails__log_back_and_state_reset(api: KubernetesApiClient, tmp_path: Path) -> None:
    project = _project(tmp_path, "\\fail")

    lines = await _collect(_executor(api), project)

    assert lines[-1] == SENTINEL_FAILED
    assert any("exited with code 12" in line for line in lines)
    build = project / "tz" / ".build" / "tz"
    assert "fake error" in (build / "main.log").read_text(encoding="utf-8")
    assert not (build / "main.fdb_latexmk").exists()


async def test__kind__missing_image__image_missing(api: KubernetesApiClient, tmp_path: Path) -> None:
    executor = _executor(api, image="registry.invalid/hds/nope:1")

    with pytest.raises(ImageMissingError):
        await _collect(executor, _project(tmp_path, "x"))

    assert await executor.sweep() == 0


async def test__kind__silent_build__idle_timeout(api: KubernetesApiClient, tmp_path: Path) -> None:
    lines = await _collect(_executor(api, idle=5), _project(tmp_path, "hang"))

    assert lines[-1] == SENTINEL_FAILED
    assert any("no output for" in line for line in lines)


async def test__kind__cancel__pod_deleted(api: KubernetesApiClient, tmp_path: Path) -> None:
    instance = f"it-{uuid.uuid4().hex[:8]}"
    executor = _executor(api, instance=instance)
    lines: list[str] = []
    task = asyncio.create_task(_collect(executor, _project(tmp_path, "hang"), lines))
    for _ in range(600):
        if any("hanging" in line for line in lines):
            break
        await asyncio.sleep(0.1)
    namespace = os.environ["HSE_TEST_K8S_NAMESPACE"]
    assert len(await api.list_pods(namespace, build_selector(instance))) == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    for _ in range(100):
        if not await api.list_pods(namespace, build_selector(instance)):
            break
        await asyncio.sleep(0.2)
    assert await api.list_pods(namespace, build_selector(instance)) == []
