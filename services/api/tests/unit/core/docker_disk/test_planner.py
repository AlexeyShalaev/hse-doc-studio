"""`DockerDiskPlanner`, собранный из конфигурации раннера: что защищено и что попадает в план."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.docker_disk.categories import studio_protected_refs
from hse_doc_studio.core.docker_disk.planner import (
    CleanupPlanRequest,
    DockerDiskPlanner,
    DockerUnavailableError,
)
from hse_doc_studio.core.docker_disk.rules import category_breakdown
from hse_doc_studio.core.docker_disk.usage import ContainerUsage, DockerDiskUsage, ImageUsage, VolumeUsage

BASE = "ghcr.io/example/studio"
RUNNER_VERSION = "2.5.0"
TEX_IMAGE = "texlive/texlive:TL2024-historic"


def _image(reference: str, category: str, *, size: int = 100, containers: int = 0) -> ImageUsage:
    repository, _, tag = reference.rpartition(":")
    return ImageUsage(
        reference=reference,
        repository=repository,
        tag=tag,
        id=f"sha256:{reference}",
        size_bytes=size,
        created="1 month ago",
        containers=containers,
        category=category,
        dangling=False,
        protected=False,
    )


class _Probe:
    """Как `DockerSystemManager`: защищает переданные ссылки и образы под контейнерами."""

    def __init__(self, usage: DockerDiskUsage) -> None:
        self._usage = usage
        self.protected_refs: frozenset[str] | None = None

    async def disk_usage(self, protected_refs: frozenset[str]) -> DockerDiskUsage:
        self.protected_refs = protected_refs
        images = [replace(i, protected=i.reference in protected_refs or i.containers > 0) for i in self._usage.images]
        return replace(self._usage, images=images)


def _runner_usage() -> DockerDiskUsage:
    return DockerDiskUsage(
        available=True,
        images=[
            _image(f"{BASE}:{RUNNER_VERSION}", "app", size=1000),
            _image(f"{BASE}:2.6.0", "app", size=1000),  # сервер на том же хосте новее раннера: не старая
            _image(f"{BASE}:2.4.0", "app", size=900),  # откат
            _image(f"{BASE}:2.3.0", "app", size=800),
            _image(f"{BASE}:latest", "app", size=1000),
            _image(TEX_IMAGE, "compile", size=5000),
            _image("texlive/texlive:TL2023-historic", "compile", size=4000),
            _image("gotenberg/gotenberg:8", "office", size=300, containers=1),
            _image("postgres:16", "other", size=400),
        ],
        containers=[
            ContainerUsage(
                name="hse-studio-updater",
                image=f"{BASE}:{RUNNER_VERSION}",
                state="exited",
                status="Exited",
                size_bytes=7,
                managed=True,
            ),
            ContainerUsage(
                name="pg", image="postgres:16", state="exited", status="Exited", size_bytes=9, managed=False
            ),
        ],
        volumes=[
            VolumeUsage(name="hse-tex-cache", size_bytes=50, links=0, managed=True),
            VolumeUsage(name="pgdata", size_bytes=60, links=1, managed=False),
        ],
        build_cache_bytes=70,
        build_cache_reclaimable_bytes=40,
        build_cache_count=3,
    )


def _runner_planner(probe: _Probe) -> DockerDiskPlanner:
    return DockerDiskPlanner(
        probe,
        protected_refs=frozenset({TEX_IMAGE}) | studio_protected_refs(BASE, RUNNER_VERSION),
        current_version=RUNNER_VERSION,
        image_base=BASE,
    )


async def test__measure__runner_config_protects_tex_image_own_version_latest_and_rollback() -> None:
    probe = _Probe(_runner_usage())

    snapshot = await _runner_planner(probe).measure()

    protected = {i.reference for i in snapshot.usage.images if i.protected}
    assert protected == {
        f"{BASE}:{RUNNER_VERSION}",
        f"{BASE}:latest",
        f"{BASE}:2.4.0",
        TEX_IMAGE,
        "gotenberg/gotenberg:8",
    }
    assert probe.protected_refs == frozenset({TEX_IMAGE, f"{BASE}:{RUNNER_VERSION}", f"{BASE}:latest"})
    # Чужое (Postgres, его контейнер и том) не видно вовсе.
    assert "postgres:16" not in {i.reference for i in snapshot.usage.images}
    assert [c.name for c in snapshot.usage.containers] == ["hse-studio-updater"]
    assert [v.name for v in snapshot.usage.volumes] == ["hse-tex-cache"]
    assert snapshot.old_versions.current_version == RUNNER_VERSION
    assert snapshot.old_versions.rollback is not None
    assert snapshot.old_versions.rollback.ref == f"{BASE}:2.4.0"
    # 2.6.0 (1000) + 2.3.0 (800) + TL2023 (4000) + updater (7) + build cache reclaimable (40)
    assert snapshot.cleanable_bytes == 5847


async def test__plan__old_versions_uses_runner_version_as_current() -> None:
    steps = await _runner_planner(_Probe(_runner_usage())).plan(CleanupPlanRequest(targets=["old_versions"]))

    assert [(s.kind, s.ref) for s in steps] == [
        ("image", f"{BASE}:2.3.0"),
        ("image", "texlive/texlive:TL2023-historic"),
        ("container", "hse-studio-updater"),
    ]


async def test__plan__everything_but_rollback_keeps_protected_and_foreign() -> None:
    steps = await _runner_planner(_Probe(_runner_usage())).plan(
        CleanupPlanRequest(
            targets=[
                "old_versions",
                "unused_images",
                "build_cache",
                "dangling_images",
                "stopped_containers",
                "runner_cache",  # не цель Docker: шаги своего кэша раннер добавит сам
            ]
        )
    )

    assert [(s.kind, s.ref) for s in steps] == [
        ("build_cache", None),
        ("dangling_images", None),
        ("image", f"{BASE}:2.6.0"),
        ("image", f"{BASE}:2.3.0"),
        ("image", "texlive/texlive:TL2023-historic"),
        ("container", "hse-studio-updater"),
    ]


async def test__plan__include_rollback_adds_the_rollback_image() -> None:
    steps = await _runner_planner(_Probe(_runner_usage())).plan(
        CleanupPlanRequest(targets=["old_versions"], include_rollback=True)
    )

    assert f"{BASE}:2.4.0" in [s.ref for s in steps]


@pytest.mark.parametrize("ref", [TEX_IMAGE, f"{BASE}:{RUNNER_VERSION}", f"{BASE}:latest", "postgres:16"])
async def test__plan__explicit_ref_outside_the_rules_is_rejected(ref: str) -> None:
    planner = _runner_planner(_Probe(_runner_usage()))

    with pytest.raises(ValueError, match="образ занят или защищён|image is in use or protected"):
        await planner.plan(CleanupPlanRequest(targets=[], images=[ref]))


async def test__plan__foreign_container_is_rejected() -> None:
    planner = _runner_planner(_Probe(_runner_usage()))

    with pytest.raises(ValueError):  # noqa: PT011 — localized message
        await planner.plan(CleanupPlanRequest(targets=[], containers=["pg"]))


async def test__plan__docker_unavailable_raises() -> None:
    planner = _runner_planner(_Probe(DockerDiskUsage(available=False)))

    with pytest.raises(DockerUnavailableError):
        await planner.plan(CleanupPlanRequest(targets=["build_cache"]))


async def test__category_breakdown__mirrors_the_frontend_bar() -> None:
    usage = DockerDiskUsage(
        available=True,
        images=[
            _image(f"{BASE}:2.5.0", "app", size=10),
            _image(TEX_IMAGE, "compile", size=20),
            replace(_image("x:1", "dangling", size=3), dangling=True),
        ],
        containers_total_bytes=4,
        volumes_total_bytes=5,
        build_cache_bytes=6,
    )

    assert category_breakdown(usage) == [("compile", 20), ("app", 10), ("cache", 6), ("runtime", 12)]
