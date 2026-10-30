"""Предел размера проекта: отказ записи, чтение и удаление работают, предупреждение с 80%, измерение сходится."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.projects.usage import (
    NoopProjectQuota,
    ProjectQuotaExceededError,
    ProjectUsage,
    QuotaPolicy,
)
from hse_doc_studio.infra.projects.usage_meter import (
    ProjectQuotaService,
    ProjectUsageSweeper,
    VolumeUsageMeasurer,
)
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.infra.storage.fs import FsObjectStore

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


class FakeUsageStore:
    def __init__(self) -> None:
        self.rows: dict[UUID, ProjectUsage] = {}

    async def get(self, project_id: UUID) -> ProjectUsage | None:
        return self.rows.get(project_id)

    async def save(self, usage: ProjectUsage) -> None:
        self.rows[usage.project_id] = usage

    async def add_tree(self, project_id: UUID, delta_bytes: int, now: datetime) -> None:
        old = self.rows[project_id]
        self.rows[project_id] = ProjectUsage(
            project_id, max(0, old.bytes_tree + delta_bytes), old.bytes_git, old.bytes_s3, old.measured_at
        )

    async def stale(self, older_than: datetime, limit: int) -> list[UUID]:
        return [pid for pid, row in self.rows.items() if row.measured_at < older_than][:limit]


class DiskMeasurer:
    """Измеритель на настоящем томе: размер берётся с диска, как в проде."""

    def __init__(self, volume: LocalDiskProjectVolume, store: FsObjectStore) -> None:
        self._inner = VolumeUsageMeasurer(volume, store, clock=lambda: _NOW)
        self.calls = 0

    async def measure(self, project_id: UUID) -> ProjectUsage:
        self.calls += 1
        return await self._inner.measure(project_id)


class World:
    def __init__(self, tmp_path: Path, limit: int) -> None:
        self.volume = LocalDiskProjectVolume(tmp_path / "projects")
        self.objects = FsObjectStore(tmp_path / "objects", max_object_bytes=10**7)
        self.project_id = uuid4()
        self.folder = self.volume.allocate(self.project_id)
        self.store = FakeUsageStore()
        self.measurer = DiskMeasurer(self.volume, self.objects)
        self.quota = ProjectQuotaService(
            self.store, self.measurer, QuotaPolicy(limit, 0.8), remeasure_min_s=0, clock=lambda: _NOW
        )

    def write(self, name: str, size: int) -> None:
        (self.folder / name).write_bytes(b"x" * size)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path, limit=1000)


async def test__check_write__over_limit__refused_with_numbers(world: World) -> None:
    world.write("a.tex", 900)

    with pytest.raises(ProjectQuotaExceededError) as err:
        await world.quota.check_write(world.project_id, 200)

    assert (err.value.used_bytes, err.value.limit_bytes, err.value.needed_bytes) == (900, 1000, 200)


async def test__check_write__fits__passes_and_record_change_moves_counter(world: World) -> None:
    world.write("a.tex", 900)
    await world.quota.check_write(world.project_id, 100)
    world.write("b.tex", 100)
    await world.quota.record_change(world.project_id, 100)

    with pytest.raises(ProjectQuotaExceededError):
        await world.quota.check_write(world.project_id, 1)


async def test__shrinking_write__passes_even_when_over_limit(world: World) -> None:
    world.write("a.tex", 1500)

    await world.quota.check_write(world.project_id, 0)
    await world.quota.check_write(world.project_id, -500)


async def test__after_delete__write_fits_again_via_remeasure(world: World) -> None:
    world.write("a.tex", 1000)
    with pytest.raises(ProjectQuotaExceededError):
        await world.quota.check_write(world.project_id, 10)

    (world.folder / "a.tex").unlink()

    await world.quota.check_write(world.project_id, 10)


async def test__remeasure__is_throttled_between_refusals(tmp_path: Path) -> None:
    world = World(tmp_path, limit=1000)
    now = [0.0]
    throttled = ProjectQuotaService(
        world.store, world.measurer, QuotaPolicy(1000), remeasure_min_s=2, clock=lambda: _NOW, monotonic=lambda: now[0]
    )
    world.write("a.tex", 1000)

    for at in (0.0, 0.5, 1.0, 5.0):
        now[0] = at
        with pytest.raises(ProjectQuotaExceededError):
            await throttled.check_write(world.project_id, 10)

    # первое измерение при первой записи (t=0) и одно повторное после паузы (t=5)
    assert world.measurer.calls == 2


async def test__status__warns_from_80_percent_and_flags_exceeded(world: World) -> None:
    world.write("a.tex", 700)
    status = await world.quota.status(world.project_id)
    assert status is not None
    assert (status.warning, status.exceeded, status.used_bytes) == (False, False, 700)

    world.write("a.tex", 800)
    await world.store.save(await world.measurer.measure(world.project_id))
    status = await world.quota.status(world.project_id)
    assert status is not None
    assert (status.warning, status.exceeded) == (True, False)

    world.write("a.tex", 1000)
    await world.store.save(await world.measurer.measure(world.project_id))
    status = await world.quota.status(world.project_id)
    assert status is not None
    assert (status.warning, status.exceeded) == (True, True)


async def test__measure__splits_tree_git_and_s3_and_ignores_symlinks(world: World, tmp_path: Path) -> None:
    world.write("a.tex", 10)
    (world.folder / ".hse-studio" / "git").mkdir(parents=True)
    (world.folder / ".hse-studio" / "git" / "pack").write_bytes(b"g" * 30)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"o" * 999)
    (world.folder / "link.bin").symlink_to(outside)
    await world.objects.put(f"artifacts/{world.project_id}/pdf/d/x.pdf", b"p" * 7)
    await world.objects.put(f"artifacts/{uuid4()}/pdf/d/other.pdf", b"p" * 50)

    usage = await world.measurer.measure(world.project_id)

    assert (usage.bytes_tree, usage.bytes_git, usage.bytes_s3) == (10, 30, 7)
    assert usage.total == 47


async def test__record_change_and_background_measure__converge(world: World) -> None:
    world.write("a.tex", 100)
    await world.quota.check_write(world.project_id, 50)
    world.write("b.tex", 50)
    await world.quota.record_change(world.project_id, 50)
    incremental = (await world.store.get(world.project_id)).bytes_tree  # type: ignore[union-attr]
    world.store.rows[world.project_id] = ProjectUsage(world.project_id, incremental, 0, 0, _NOW - timedelta(hours=2))

    sweeper = ProjectUsageSweeper(
        world.store, world.measurer, max_age=timedelta(hours=1), batch_size=5, pause_s=0, clock=lambda: _NOW
    )
    assert await sweeper.run() == 1

    measured = await world.store.get(world.project_id)
    assert measured is not None
    assert measured.bytes_tree == incremental == 150
    assert measured.measured_at == _NOW


async def test__noop_quota__never_refuses() -> None:
    quota = NoopProjectQuota()
    await quota.check_write(uuid4(), 10**15)
    assert quota.enabled is False
    assert await quota.status(uuid4()) is None


async def test__unlimited_policy__disabled() -> None:
    quota = ProjectQuotaService(FakeUsageStore(), DiskMeasurerStub(), QuotaPolicy(0))
    assert quota.enabled is False
    await quota.check_write(uuid4(), 10**15)
    assert await quota.status(uuid4()) is None


class DiskMeasurerStub:
    async def measure(self, project_id: UUID) -> ProjectUsage:
        raise AssertionError("не должен вызываться")
