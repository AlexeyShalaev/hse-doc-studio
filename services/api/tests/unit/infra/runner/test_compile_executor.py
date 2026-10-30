"""Compile на раннере: манифест, сборка в поддельном docker, выход PDF, отмена и недостающий образ."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.jobs.entities import compile_payload_of
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.errors import JobFailure
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.jobs.wire import JobEnvelope
from hse_doc_studio.infra.di.containers.runner import create_runner_container
from hse_doc_studio.infra.docker.cli import configure_docker_binary
from hse_doc_studio.infra.jobs.embedded_runner import EmbeddedCompileRunner
from hse_doc_studio.infra.runner.capabilities import detect_tags
from hse_doc_studio.infra.runner.compile_executor import CompileJobExecutor, RoutingJobExecutor
from hse_doc_studio.infra.runner.config import RunnerConfig
from hse_doc_studio.infra.runner.executor import JobContext
from hse_doc_studio.infra.runner.settings import RunnerSettingsRepository
from hse_doc_studio.infra.runner.workspace import BlobCache, RunnerWorkspaces

from tests.unit.core.jobs.samples import make_compile_spec, make_verify_spec
from tests.unit.infra.runner.fake_docker import install_fake_docker, recorded_calls

_SOURCE = b"\\documentclass{article}"


class _Fetcher:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self._blobs = blobs

    @contextlib.contextmanager
    def bind(self, job_id: str, job_token: str) -> Iterator[None]:
        yield

    async def __call__(self, sha256: str) -> bytes:
        return self._blobs[sha256]


@pytest.fixture
def docker_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    monkeypatch.setenv("FAKE_DOCKER_LOG", str(log))
    monkeypatch.setenv("FAKE_DOCKER_PID", str(tmp_path / "pid"))
    configure_docker_binary(str(install_fake_docker(bin_dir)))
    yield log
    configure_docker_binary(None)


def _config(tmp_path: Path, **extra: Any) -> RunnerConfig:
    return RunnerConfig(api_url="http://api", token="t", data_dir=tmp_path / "runner", **extra)  # type: ignore[arg-type]


async def _executor(config: RunnerConfig) -> tuple[CompileJobExecutor, AsyncIterator[None] | None]:
    container = create_runner_container(config)
    runner = await container.get(EmbeddedCompileRunner)
    sha = hashlib.sha256(_SOURCE).hexdigest()
    fetcher = _Fetcher({sha: _SOURCE})
    cache = BlobCache(config.data_dir, fetcher)  # type: ignore[arg-type]
    executor = CompileJobExecutor(
        workspaces=RunnerWorkspaces(config.data_dir, cache),
        cache=cache,
        fetcher=fetcher,  # type: ignore[arg-type]
        runner=runner,
        cache_max_bytes=1 << 20,
    )
    return executor, None


def _envelope(*, passes: int = 7) -> JobEnvelope:
    spec = make_compile_spec()
    payload = replace(compile_payload_of(spec), default_passes=passes)
    manifest = (ManifestFile("tz/main.tex", hashlib.sha256(_SOURCE).hexdigest(), len(_SOURCE)),)
    return JobEnvelope(replace(spec, payload=payload), manifest, 600.0, 1, "token")


def _ctx(lines: list[str] | None = None) -> JobContext:
    sink = lines if lines is not None else []
    return JobContext(log=sink.append, cancelled=asyncio.Event())


async def test__execute__builds_in_isolated_container_and_returns_the_pdf(tmp_path: Path, docker_log: Path) -> None:
    executor, _ = await _executor(_config(tmp_path))
    lines: list[str] = []

    outcome = await executor.execute(_envelope(passes=7), _ctx(lines))

    assert outcome.result.status is JobStatus.succeeded
    assert outcome.result.data.build_ok is True  # type: ignore[union-attr]
    assert outcome.result.data.pages == 3  # type: ignore[union-attr]
    assert outcome.result.data.words == 6  # type: ignore[union-attr]
    assert [o.ref.path for o in outcome.outputs] == ["tz/main.pdf"]
    assert outcome.outputs[0].path.read_bytes() == b"%PDF-1.5 built"
    latexmk = next(call for call in recorded_calls(docker_log) if "latexmk" in call)
    assert "$max_repeat=7;" in latexmk
    assert latexmk[latexmk.index("--network") + 1] == "none"
    assert "--read-only" in latexmk
    assert any("latexmk ok" in line for line in lines)


async def test__execute__isolation_off__runner_argv_matches_the_embedded_profile(
    tmp_path: Path, docker_log: Path
) -> None:
    executor, _ = await _executor(_config(tmp_path, isolation=False))

    await executor.execute(_envelope(), _ctx())

    latexmk = next(call for call in recorded_calls(docker_log) if "latexmk" in call)
    assert "--network" not in latexmk
    assert "--read-only" not in latexmk


async def test__execute__latexmk_fails__failed_result_without_outputs(
    tmp_path: Path, docker_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_MODE", "fail")
    executor, _ = await _executor(_config(tmp_path))
    lines: list[str] = []

    outcome = await executor.execute(_envelope(), _ctx(lines))

    assert outcome.result.status is JobStatus.failed
    assert outcome.result.data.build_ok is False  # type: ignore[union-attr]
    assert outcome.outputs == ()
    assert any("boom" in line for line in lines)


async def test__execute__image_missing__typed_failure_before_any_build(
    tmp_path: Path, docker_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_MODE", "no_image")
    executor, _ = await _executor(_config(tmp_path, tex_image="tex:TL2024"))

    with pytest.raises(JobFailure) as caught:
        await executor.execute(_envelope(), _ctx())

    assert caught.value.error.code == "image_missing"
    assert caught.value.error.detail == "tex:TL2024"
    assert not [call for call in recorded_calls(docker_log) if "latexmk" in call]


async def test__execute__cancelled__container_process_is_killed(
    tmp_path: Path, docker_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_DOCKER_MODE", "hang")
    executor, _ = await _executor(_config(tmp_path))
    lines: list[str] = []
    pid_file = tmp_path / "pid"

    task = asyncio.create_task(executor.execute(_envelope(), _ctx(lines)))
    for _ in range(400):
        if pid_file.exists() and any("started" in line for line in lines):
            break
        await asyncio.sleep(0.025)
    pid = int(pid_file.read_text())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    for _ in range(200):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.025)
    else:
        pytest.fail("docker process is still alive after cancel")


async def test__routing__compile_goes_to_compile_executor_the_rest_to_handlers() -> None:
    seen: list[str] = []

    class _Named:
        def __init__(self, name: str) -> None:
            self._name = name

        async def execute(self, envelope: JobEnvelope, ctx: JobContext) -> Any:
            seen.append(self._name)

    router = RoutingJobExecutor(_Named("compile"), _Named("handlers"))  # type: ignore[arg-type]
    other = replace(_envelope(), spec=make_verify_spec())

    await router.execute(_envelope(), _ctx())
    await router.execute(other, _ctx())

    assert seen == ["compile", "handlers"]


async def test__settings__slots_follow_concurrency_and_saving_is_refused(tmp_path: Path) -> None:
    repo = RunnerSettingsRepository(_config(tmp_path, concurrency=3))

    assert await repo.get() == {"max_concurrent_compiles": 3}
    with pytest.raises(RuntimeError):
        await repo.save({})


def test__tags__docker_gives_the_tex_tag() -> None:
    assert "tex" in detect_tags(office_url=None, tex_available=True, archive_available=lambda fmt: False)
    assert "tex" not in detect_tags(office_url=None, archive_available=lambda fmt: False)
