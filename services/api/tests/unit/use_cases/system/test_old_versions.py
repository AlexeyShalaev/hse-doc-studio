"""Что считается «старой версией» и что очистка имеет право убрать."""

from __future__ import annotations

import pytest
from hse_doc_studio.infra.docker.cleanup_jobs import CleanupBusyError, CleanupJob, CleanupStep
from hse_doc_studio.infra.docker.system_manager import ContainerUsage, DockerDiskUsage, ImageUsage
from hse_doc_studio.use_cases.system.cleanup_docker import StartDockerCleanupInput, StartDockerCleanupUC
from hse_doc_studio.use_cases.system.get_docker_disk_usage import GetDockerDiskUsageUC
from hse_doc_studio.use_cases.system.old_versions import find_old_versions

BASE = "registry.example/studio"
CURRENT = "2.5.0"
COMPILE_REPO = "texlive/texlive"


def _image(repository: str, tag: str, **overrides: object) -> ImageUsage:
    defaults: dict[str, object] = {
        "reference": f"{repository}:{tag}",
        "repository": repository,
        "tag": tag,
        "id": f"sha256:{repository}{tag}",
        "size_bytes": 100,
        "created": "1 month ago",
        "containers": 0,
        "category": "app" if repository == BASE else "compile",
        "dangling": False,
        "protected": False,
    }
    defaults.update(overrides)
    return ImageUsage(**defaults)  # type: ignore[arg-type]


def _studio(tag: str, **overrides: object) -> ImageUsage:
    return _image(BASE, tag, **overrides)


def _usage(images: list[ImageUsage], containers: list[ContainerUsage] | None = None) -> DockerDiskUsage:
    return DockerDiskUsage(available=True, images=images, containers=containers or [])


def _updater(state: str = "exited") -> ContainerUsage:
    return ContainerUsage(
        name="hse-studio-updater", image=f"{BASE}:{CURRENT}", state=state, status="Exited", size_bytes=7, managed=True
    )


def test__find_old_versions__latest_previous_is_rollback_and_older_are_items() -> None:
    usage = _usage(
        [
            _studio(CURRENT, protected=True),
            _studio("2.4.1"),
            _studio("2.4.0"),
            _studio("2.3.9"),
            _studio("2.10.0-rc.1"),  # newer than current: never old
            _studio("latest", protected=True),
            _studio("sha-abc123"),  # no version: never old
        ]
    )
    old = find_old_versions(usage, CURRENT, BASE)
    assert old.rollback is not None
    assert old.rollback.ref == f"{BASE}:2.4.1"
    assert old.refs == [f"{BASE}:2.4.0", f"{BASE}:2.3.9"]
    assert old.reclaimable_bytes == 200
    assert old.rollback_bytes == 100


def test__find_old_versions__images_in_use_are_never_items() -> None:
    usage = _usage([_studio("2.4.0"), _studio("2.3.0", containers=1, protected=True), _studio("2.2.0")])
    old = find_old_versions(usage, CURRENT, BASE)
    assert old.rollback is not None
    assert old.rollback.ref == f"{BASE}:2.4.0"
    assert old.refs == [f"{BASE}:2.2.0"]


def test__find_old_versions__stale_service_tags_only_next_to_a_live_tag() -> None:
    usage = _usage(
        [
            _image(COMPILE_REPO, "2025", protected=True),
            _image(COMPILE_REPO, "2023"),
            _image(COMPILE_REPO, "2022", containers=1, protected=True),
            _image("other/service", "1", category="compile"),  # no live tag in its repo
        ]
    )
    old = find_old_versions(usage, CURRENT, BASE)
    assert old.refs == [f"{COMPILE_REPO}:2023"]
    assert old.rollback is None


def test__find_old_versions__stopped_updater_listed_running_one_not() -> None:
    assert find_old_versions(_usage([], [_updater()]), CURRENT, BASE).refs == ["hse-studio-updater"]
    assert find_old_versions(_usage([], [_updater("running")]), CURRENT, BASE).refs == []


def test__find_old_versions__docker_unavailable_is_empty() -> None:
    old = find_old_versions(DockerDiskUsage(available=False), CURRENT, BASE)
    assert old.rollback is None
    assert old.items == []


# -- use cases over a fake docker -------------------------------------------------


class _FakeManager:
    def __init__(self, usage: DockerDiskUsage) -> None:
        self._usage = usage

    async def disk_usage(self, protected_refs: frozenset[str]) -> DockerDiskUsage:
        return self._usage


class _FakeJobs:
    def __init__(self, busy: bool = False) -> None:
        self.steps: list[CleanupStep] = []
        self._busy = busy

    async def start(self, steps: list[CleanupStep]) -> CleanupJob:
        if self._busy:
            raise CleanupBusyError
        self.steps = steps
        return CleanupJob(id="job", status="running", steps=steps)


class _Settings:
    async def get(self) -> dict[str, object]:
        return {}


def _usage_uc(usage: DockerDiskUsage) -> GetDockerDiskUsageUC:
    return GetDockerDiskUsageUC(
        manager=_FakeManager(usage),  # type: ignore[arg-type]
        settings_repo=_Settings(),  # type: ignore[arg-type]
        default_images={},
        always_protected=frozenset({f"{BASE}:{CURRENT}"}),
        current_version=CURRENT,
        image_base=BASE,
    )


def _start_uc(usage: DockerDiskUsage, jobs: _FakeJobs) -> StartDockerCleanupUC:
    return StartDockerCleanupUC(
        manager=_FakeManager(usage),  # type: ignore[arg-type]
        jobs=jobs,  # type: ignore[arg-type]
        settings_repo=_Settings(),  # type: ignore[arg-type]
        default_images={},
        always_protected=frozenset({f"{BASE}:{CURRENT}"}),
        current_version=CURRENT,
        image_base=BASE,
    )


def _fixture_usage() -> DockerDiskUsage:
    return _usage(
        [
            _studio(CURRENT, protected=True),
            _studio("2.4.0"),
            _studio("2.3.0"),
            _studio("2.2.0", containers=1, protected=True),
        ],
        [_updater()],
    )


@pytest.mark.asyncio
async def test__usage__rollback_is_protected_and_not_counted_as_cleanable() -> None:
    out = await _usage_uc(_fixture_usage()).execute()
    by_ref = {i.reference: i for i in out.usage.images}
    assert by_ref[f"{BASE}:2.4.0"].protected
    assert not by_ref[f"{BASE}:2.3.0"].protected
    assert out.old_versions.rollback is not None
    # 2.3.0 (100) + stopped updater (7)
    assert out.cleanable_bytes == 107


@pytest.mark.asyncio
async def test__cleanup_old_versions__keeps_current_rollback_and_busy_images() -> None:
    jobs = _FakeJobs()
    await _start_uc(_fixture_usage(), jobs).execute(StartDockerCleanupInput(targets=["old_versions"]))
    assert [(s.kind, s.ref) for s in jobs.steps] == [
        ("image", f"{BASE}:2.3.0"),
        ("container", "hse-studio-updater"),
    ]


@pytest.mark.asyncio
async def test__cleanup_old_versions__include_rollback_adds_only_the_rollback() -> None:
    jobs = _FakeJobs()
    await _start_uc(_fixture_usage(), jobs).execute(
        StartDockerCleanupInput(targets=["old_versions"], include_rollback=True)
    )
    refs = [s.ref for s in jobs.steps if s.kind == "image"]
    assert refs == [f"{BASE}:2.3.0", f"{BASE}:2.4.0"]


@pytest.mark.asyncio
async def test__cleanup_unused_images__never_takes_the_rollback_even_with_flag() -> None:
    jobs = _FakeJobs()
    await _start_uc(_fixture_usage(), jobs).execute(
        StartDockerCleanupInput(targets=["unused_images"], include_rollback=True)
    )
    assert [s.ref for s in jobs.steps] == [f"{BASE}:2.3.0"]


@pytest.mark.asyncio
async def test__cleanup__explicit_rollback_or_busy_image_is_rejected() -> None:
    uc = _start_uc(_fixture_usage(), _FakeJobs())
    for ref in (f"{BASE}:2.4.0", f"{BASE}:2.2.0", f"{BASE}:{CURRENT}"):
        with pytest.raises(ValueError):  # noqa: PT011 — localized message
            await uc.execute(StartDockerCleanupInput(targets=[], images=[ref]))


@pytest.mark.asyncio
async def test__cleanup__docker_unavailable_is_refused() -> None:
    uc = _start_uc(DockerDiskUsage(available=False), _FakeJobs())
    with pytest.raises(ValueError):  # noqa: PT011
        await uc.execute(StartDockerCleanupInput(targets=["old_versions"]))
