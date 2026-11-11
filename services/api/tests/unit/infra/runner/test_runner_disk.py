"""`RunnerDiskService`: отчёт о диске раннера и очистка по целям на фейковом Docker (storage-cleanup.md, 5.1, 5.2)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hse_doc_studio import __version__
from hse_doc_studio.api.schemas.runner import RunnerDiskReportBody
from hse_doc_studio.core.docker_disk.categories import studio_protected_refs
from hse_doc_studio.core.docker_disk.planner import DockerDiskPlanner
from hse_doc_studio.core.docker_disk.usage import (
    CleanupResult,
    ContainerUsage,
    DockerDiskUsage,
    ImageUsage,
    VolumeUsage,
)
from hse_doc_studio.core.jobs.codec import decode, encode
from hse_doc_studio.core.jobs.disk import (
    MAX_DISK_REPORT_BYTES,
    MAX_LISTED_ITEMS,
    CommandProgress,
    CommandStepKind,
    CommandStepStatus,
    DiskCategoryKey,
    DiskCleanupPayload,
    DiskTarget,
    DockerDiskReason,
    RunnerCommandState,
    RunnerDiskReport,
)
from hse_doc_studio.core.jobs.runners import RunnerHostKind
from hse_doc_studio.infra.runner.config import BuildExecutorKind, RunnerConfig
from hse_doc_studio.infra.runner.disk import (
    DiskCleanupBusyError,
    RunnerDiskService,
    RunnerDocker,
    build_runner_disk_service,
    runner_docker,
)
from hse_doc_studio.infra.runner.workspace import BlobCache, RunnerWorkspaces

BASE = "ghcr.io/example/studio"
VERSION = "2.5.0"
TEX = "texlive/texlive:TL2024-historic"
NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)


def _image(reference: str, category: str, *, size: int = 100, containers: int = 0) -> ImageUsage:
    dangling = category == "dangling"
    repository, _, tag = ("", "", "") if dangling else reference.rpartition(":")
    return ImageUsage(
        reference=reference,
        repository=repository,
        tag=tag,
        id=f"sha256:{reference}",
        size_bytes=size,
        created="1 month ago",
        containers=containers,
        category=category,
        dangling=dangling,
        protected=False,
    )


class _Probe:
    """Как `DockerSystemManager.disk_usage`: защищает переданные ссылки и занятые образы; можно придержать."""

    def __init__(self, usage: DockerDiskUsage) -> None:
        self.usage = usage
        self.gate: asyncio.Event | None = None
        self.calls = 0

    async def disk_usage(self, protected_refs: frozenset[str]) -> DockerDiskUsage:
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        images = [replace(i, protected=i.reference in protected_refs or i.containers > 0) for i in self.usage.images]
        return replace(self.usage, images=images)


class _System:
    """Исполнитель шагов Docker: пишет вызовы, может придержать первый шаг."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.gate: asyncio.Event | None = None
        self.started = asyncio.Event()
        self.image_error: str | None = None

    async def _step(self, name: str) -> None:
        self.calls.append(name)
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()

    async def prune_build_cache(self) -> CleanupResult:
        await self._step("build_cache")
        return CleanupResult(target="build_cache", freed_bytes=40)

    async def prune_dangling_images(self) -> CleanupResult:
        await self._step("dangling_images")
        return CleanupResult(target="dangling_images", freed_bytes=30)

    async def remove_images(self, references: list[str], target: str = "unused_images") -> CleanupResult:
        await self._step(f"image:{references[0]}")
        if self.image_error is not None:
            return CleanupResult(target=target, freed_bytes=0, errors=[self.image_error])
        return CleanupResult(target=target, freed_bytes=100, removed=references)

    async def remove_stopped_managed_container(self, name: str) -> CleanupResult:
        await self._step(f"container:{name}")
        return CleanupResult(target="container", freed_bytes=7, removed=[name])


def _usage() -> DockerDiskUsage:
    return DockerDiskUsage(
        available=True,
        images=[
            _image(f"{BASE}:{VERSION}", "app", size=1000),
            _image(f"{BASE}:2.4.0", "app", size=900),  # откат
            _image(f"{BASE}:2.3.0", "app", size=800),
            _image(TEX, "compile", size=5000),
            _image("texlive/texlive:TL2023-historic", "compile", size=4000),
            _image("gotenberg/gotenberg:8", "office", size=300, containers=1),
            _image("sha256:dead", "dangling", size=20),
            _image("postgres:16", "other", size=400),
        ],
        containers=[
            ContainerUsage(
                name="hse-studio-updater",
                image=f"{BASE}:2.3.0",
                state="exited",
                status="Exited",
                size_bytes=7,
                managed=True,
            ),
            ContainerUsage(name="pg", image="postgres:16", state="running", status="Up", size_bytes=9, managed=False),
        ],
        volumes=[
            VolumeUsage(name="hse-tex-cache", size_bytes=50, links=0, managed=True),
            VolumeUsage(name="pgdata", size_bytes=60, links=1, managed=False),
        ],
        images_total_bytes=12420,
        containers_total_bytes=16,
        volumes_total_bytes=110,
        build_cache_bytes=70,
        build_cache_reclaimable_bytes=40,
        build_cache_count=3,
    )


def _docker(probe: _Probe, system: _System) -> RunnerDocker:
    planner = DockerDiskPlanner(
        probe,
        protected_refs=frozenset({TEX}) | studio_protected_refs(BASE, VERSION),
        current_version=VERSION,
        image_base=BASE,
    )
    return RunnerDocker(planner=planner, system=system)  # type: ignore[arg-type]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _fetch(_sha256: str) -> bytes:
    raise AssertionError("not expected")


def _service(tmp_path: Path, docker: RunnerDocker | DockerDiskReason) -> RunnerDiskService:
    cache = BlobCache(tmp_path, _fetch)
    return RunnerDiskService(
        cache=cache,
        workspaces=RunnerWorkspaces(tmp_path, cache),
        data_dir=tmp_path,
        blobs_limit_bytes=2048,
        workspaces_limit_bytes=4096,
        docker=docker,
        clock=lambda: NOW,
    )


def _seed_cache(tmp_path: Path) -> None:
    """Старый блоб на 11 байт и одна рабочая копия на 5."""
    blob = tmp_path / "blobs" / "ab" / _sha(b"old")
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(b"old content")
    then = time.time() - 3600
    os.utime(blob, (then, then))
    project = tmp_path / "workspaces" / "p1"
    project.mkdir(parents=True, exist_ok=True)
    (project / "main.tex").write_bytes(b"12345")


def _roundtrip(report: RunnerDiskReport) -> None:
    body = encode(report)
    assert decode(RunnerDiskReport, body) == report
    RunnerDiskReportBody.model_validate(body)


async def test__measure__docker_runner_reports_studio_footprint_cache_and_volume(tmp_path: Path) -> None:
    _seed_cache(tmp_path)
    service = _service(tmp_path, _docker(_Probe(_usage()), _System()))

    report = await service.measure()

    _roundtrip(report)
    assert report.measured_at == NOW
    assert report.targets == tuple(DiskTarget)
    assert report.docker_reason is None
    docker = report.docker
    assert docker is not None
    assert docker.available
    assert [(c.key, c.bytes) for c in docker.categories] == [
        (DiskCategoryKey.compile, 9000),
        (DiskCategoryKey.office, 300),
        (DiskCategoryKey.app, 2700),
        (DiskCategoryKey.cache, 70),
        (DiskCategoryKey.runtime, 20 + 7 + 50),
    ]
    # Чужое (Postgres, его контейнер и том) не видно и в итог не входит.
    assert docker.total_bytes == sum(c.bytes for c in docker.categories)
    assert [(i.ref, i.size_bytes) for i in docker.unused_images] == [
        ("texlive/texlive:TL2023-historic", 4000),
        (f"{BASE}:2.3.0", 800),
    ]
    assert not docker.unused_truncated
    # TL2023 (4000) + 2.3.0 (800) + висячий (20) + updater (7) + build cache reclaimable (40); откат защищён.
    assert docker.cleanable_bytes == 4867
    assert (docker.dangling.bytes, docker.dangling.count) == (20, 1)
    assert (docker.stopped_containers.bytes, docker.stopped_containers.count) == (7, 1)
    assert (docker.build_cache.bytes, docker.build_cache.reclaimable_bytes, docker.build_cache.count) == (70, 40, 3)
    old = docker.old_versions
    assert old.current_version == VERSION
    assert old.rollback is not None
    assert (old.rollback.ref, old.rollback.version) == (f"{BASE}:2.4.0", "2.4.0")
    assert {item.ref for item in old.items} == {
        f"{BASE}:2.3.0",
        "texlive/texlive:TL2023-historic",
        "hse-studio-updater",
    }
    assert old.rollback_bytes == 900
    assert [(v.name, v.size_bytes) for v in docker.volumes] == [("hse-tex-cache", 50)]
    assert (report.cache.blobs.bytes, report.cache.blobs.count, report.cache.blobs.limit_bytes) == (11, 1, 2048)
    workspaces = report.cache.workspaces
    assert (workspaces.bytes, workspaces.count, workspaces.limit_bytes, workspaces.busy) == (5, 1, 4096, 0)
    assert report.volume is not None
    assert 0 <= report.volume.free_bytes <= report.volume.total_bytes


@pytest.mark.parametrize(
    ("executor", "host_kind", "reason"),
    [
        (BuildExecutorKind.kubernetes, RunnerHostKind.cli, DockerDiskReason.kubernetes),
        (BuildExecutorKind.docker, RunnerHostKind.desktop, DockerDiskReason.managed_locally),
    ],
)
async def test__measure__kubernetes_and_desktop_report_only_runner_cache(
    tmp_path: Path, executor: BuildExecutorKind, host_kind: RunnerHostKind, reason: DockerDiskReason
) -> None:
    _seed_cache(tmp_path)
    config = RunnerConfig(api_url="http://studio", data_dir=tmp_path, executor=executor, host_kind=host_kind)
    cache = BlobCache(tmp_path, _fetch)
    service = build_runner_disk_service(config, cache, RunnerWorkspaces(tmp_path, cache))

    report = await service.measure()

    _roundtrip(report)
    assert report.docker is None
    assert report.docker_reason is reason
    assert report.targets == (DiskTarget.runner_cache,)
    assert report.cache.blobs.limit_bytes == config.cache_max_bytes
    assert report.cache.workspaces.limit_bytes == config.workspaces_max_bytes
    assert report.cache.workspaces.count == 1


def test__runner_docker__built_from_runner_config() -> None:
    config = RunnerConfig(
        api_url="http://studio", tex_image="registry.local:5000/tex/live:TL2024", image_base=BASE, tex_cache_volume="tc"
    )

    docker = runner_docker(config)

    assert docker.planner.protected_refs == frozenset(
        {"registry.local:5000/tex/live:TL2024", f"{BASE}:{__version__}", f"{BASE}:latest"}
    )
    assert docker.system._category_by_repo["registry.local:5000/tex/live"] == "compile"
    assert docker.system._app_repo_prefix == BASE
    assert "tc" in docker.system._managed_volume_names


@pytest.mark.parametrize("broken", [False, True])
async def test__measure__unreachable_docker_leaves_only_runner_cache(tmp_path: Path, broken: bool) -> None:
    probe = _Probe(DockerDiskUsage(available=False))
    if broken:

        async def boom(_protected: frozenset[str]) -> DockerDiskUsage:
            raise RuntimeError("garbage from docker")

        probe.disk_usage = boom  # type: ignore[method-assign]
    service = _service(tmp_path, _docker(probe, _System()))

    report = await service.measure()

    _roundtrip(report)
    assert report.docker is not None
    assert not report.docker.available
    assert report.docker_reason is None
    assert report.targets == (DiskTarget.runner_cache,)


async def test__measure__thousand_long_images_are_cut_to_fit_64_kib(tmp_path: Path) -> None:
    # Ссылки на пределе разумного: сто строк каждого списка вместе в 64 КБ не влезают, режем дальше.
    long_repo = "registry.example.org:5000/" + "x" * 300
    long_base = "registry.example.org:5000/" + "s" * 300
    images = [_image(f"{long_base}:{VERSION}", "app")]
    images += [_image(f"{long_repo}:t{n}", "compile", size=1000 + n) for n in range(1000)]
    images += [_image(f"{long_base}:0.{n}.0", "app", size=10) for n in range(1, 1000)]
    probe = _Probe(DockerDiskUsage(available=True, images=images, images_total_bytes=1))
    planner = DockerDiskPlanner(
        probe,
        protected_refs=frozenset({f"{long_repo}:t999"}) | studio_protected_refs(long_base, VERSION),
        current_version=VERSION,
        image_base=long_base,
    )
    service = _service(tmp_path, RunnerDocker(planner=planner, system=_System()))  # type: ignore[arg-type]

    report = await service.measure()

    assert len(json.dumps(encode(report)).encode()) <= MAX_DISK_REPORT_BYTES
    _roundtrip(report)
    docker = report.docker
    assert docker is not None
    assert docker.unused_truncated
    assert 0 < len(docker.unused_images) < MAX_LISTED_ITEMS
    assert 0 < len(docker.old_versions.items) < MAX_LISTED_ITEMS
    # Самые большие сверху, итоги по всем, а не по показанным.
    assert docker.unused_images[0].ref == f"{long_repo}:t998"
    snapshot = await planner.measure()
    assert docker.cleanable_bytes == snapshot.cleanable_bytes
    assert docker.old_versions.reclaimable_bytes == snapshot.old_versions.reclaimable_bytes
    assert docker.old_versions.reclaimable_bytes > sum(item.size_bytes for item in docker.old_versions.items)


async def _collect(
    service: RunnerDiskService, payload: DiskCleanupPayload
) -> tuple[list[tuple[RunnerCommandState, CommandProgress]], RunnerCommandState, CommandProgress]:
    seen: list[tuple[RunnerCommandState, CommandProgress]] = []

    async def observe(state: RunnerCommandState, progress: CommandProgress) -> None:
        seen.append((state, progress))

    run = service.cleanup(payload, observe)
    outcome = await run.wait()
    return seen, outcome.state, outcome.progress


async def test__cleanup__all_targets_run_docker_plan_and_runner_cache(tmp_path: Path) -> None:
    _seed_cache(tmp_path)
    system = _System()
    service = _service(tmp_path, _docker(_Probe(_usage()), system))
    payload = DiskCleanupPayload(targets=tuple(DiskTarget))

    seen, state, progress = await _collect(service, payload)

    assert state is RunnerCommandState.done
    assert [(s.kind, s.ref, s.status) for s in progress.steps] == [
        (CommandStepKind.build_cache, None, CommandStepStatus.done),
        (CommandStepKind.dangling_images, None, CommandStepStatus.done),
        (CommandStepKind.image, f"{BASE}:2.3.0", CommandStepStatus.done),
        (CommandStepKind.image, "texlive/texlive:TL2023-historic", CommandStepStatus.done),
        (CommandStepKind.container, "hse-studio-updater", CommandStepStatus.done),
        (CommandStepKind.runner_blobs, None, CommandStepStatus.done),
        (CommandStepKind.runner_workspaces, None, CommandStepStatus.done),
    ]
    # Откат и активные образы не тронуты.
    assert f"image:{BASE}:2.4.0" not in system.calls
    assert f"image:{TEX}" not in system.calls
    assert [s.freed_bytes for s in progress.steps[-2:]] == [11, 5]
    assert progress.freed_bytes == 40 + 30 + 100 + 100 + 7 + 11 + 5
    assert progress.error is None
    assert all(s is RunnerCommandState.running for s, _ in seen[:-1])
    assert seen[-1] == (RunnerCommandState.done, progress)
    assert not (tmp_path / "workspaces" / "p1").exists()
    assert service.current() is not None


async def test__cleanup__rollback_only_by_flag(tmp_path: Path) -> None:
    system = _System()
    service = _service(tmp_path, _docker(_Probe(_usage()), system))

    await service.cleanup(DiskCleanupPayload(targets=(DiskTarget.old_versions,), include_rollback=True)).wait()

    assert f"image:{BASE}:2.4.0" in system.calls
    assert f"image:{BASE}:{VERSION}" not in system.calls


async def test__cleanup__docker_target_on_kubernetes_is_an_error_runner_cache_still_cleans(tmp_path: Path) -> None:
    _seed_cache(tmp_path)
    service = _service(tmp_path, DockerDiskReason.kubernetes)
    payload = DiskCleanupPayload(targets=(DiskTarget.build_cache, DiskTarget.runner_cache))

    _, state, progress = await _collect(service, payload)

    assert state is RunnerCommandState.error
    assert progress.error is not None
    assert "build_cache" in progress.error
    assert [s.kind for s in progress.steps] == [CommandStepKind.runner_blobs, CommandStepKind.runner_workspaces]
    assert progress.freed_bytes == 16


async def test__cleanup__unavailable_docker_is_an_error(tmp_path: Path) -> None:
    service = _service(tmp_path, _docker(_Probe(DockerDiskUsage(available=False)), _System()))

    _, state, progress = await _collect(service, DiskCleanupPayload(targets=(DiskTarget.dangling_images,)))

    assert state is RunnerCommandState.error
    assert progress.steps == ()
    assert progress.error


async def test__cleanup__nothing_to_do_is_done_with_no_steps(tmp_path: Path) -> None:
    usage = replace(_usage(), images=[_image(f"{BASE}:{VERSION}", "app")], containers=[])
    service = _service(tmp_path, _docker(_Probe(usage), _System()))

    seen, state, progress = await _collect(service, DiskCleanupPayload(targets=(DiskTarget.unused_images,)))

    assert state is RunnerCommandState.done
    assert progress == CommandProgress(steps=(), freed_bytes=0, error=None)
    assert seen == [(RunnerCommandState.done, progress)]


async def test__cleanup__step_error_is_one_short_line(tmp_path: Path) -> None:
    system = _System()
    system.image_error = f"{BASE}:2.3.0: conflict\n" + "y" * 500
    service = _service(tmp_path, _docker(_Probe(_usage()), system))

    _, state, progress = await _collect(service, DiskCleanupPayload(targets=(DiskTarget.unused_images,)))

    assert state is RunnerCommandState.error
    errors = [s.error for s in progress.steps if s.status is CommandStepStatus.error]
    assert errors
    assert all(e is not None and len(e) <= 300 and "\n" not in e for e in errors)


async def test__cleanup__cancel_stops_after_current_step(tmp_path: Path) -> None:
    system = _System()
    system.gate = asyncio.Event()
    service = _service(tmp_path, _docker(_Probe(_usage()), system))
    run = service.cleanup(DiskCleanupPayload(targets=(DiskTarget.build_cache, DiskTarget.dangling_images)))
    await system.started.wait()

    assert run.state is RunnerCommandState.running
    assert run.progress.steps[0].status is CommandStepStatus.running
    with pytest.raises(DiskCleanupBusyError):
        service.cleanup(DiskCleanupPayload(targets=(DiskTarget.runner_cache,)))
    run.cancel()
    system.gate.set()
    outcome = await run.wait()

    assert outcome.state is RunnerCommandState.cancelled
    assert [s.status for s in outcome.progress.steps] == [CommandStepStatus.done, CommandStepStatus.skipped]
    assert system.calls == ["build_cache"]
    # Следующая очистка после итога разрешена.
    await service.cleanup(DiskCleanupPayload(targets=(DiskTarget.runner_cache,))).wait()


async def test__cleanup__cancel_during_measure_runs_nothing(tmp_path: Path) -> None:
    probe = _Probe(_usage())
    probe.gate = asyncio.Event()
    system = _System()
    service = _service(tmp_path, _docker(probe, system))
    run = service.cleanup(DiskCleanupPayload(targets=(DiskTarget.build_cache, DiskTarget.runner_cache)))
    await asyncio.sleep(0)

    run.cancel()
    probe.gate.set()
    outcome = await run.wait()

    assert outcome.state is RunnerCommandState.cancelled
    assert {s.status for s in outcome.progress.steps} == {CommandStepStatus.skipped}
    assert len(outcome.progress.steps) == 3
    assert system.calls == []


async def test__cleanup__failing_observer_does_not_stop_cleanup(tmp_path: Path) -> None:
    service = _service(tmp_path, _docker(_Probe(_usage()), _System()))

    async def broken(_state: RunnerCommandState, _progress: CommandProgress) -> None:
        raise RuntimeError("network down")

    outcome = await service.cleanup(DiskCleanupPayload(targets=(DiskTarget.build_cache,)), broken).wait()

    assert outcome.state is RunnerCommandState.done
    assert outcome.progress.freed_bytes == 40
