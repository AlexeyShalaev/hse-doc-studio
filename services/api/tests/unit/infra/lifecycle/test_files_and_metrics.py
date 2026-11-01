"""Файловый источник (состояние совместной правки) и метрики жизненного цикла для /metrics."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hse_doc_studio.api.observability.lifecycle_metrics import lifecycle_collector
from hse_doc_studio.core.lifecycle.disk import SafeMode
from hse_doc_studio.core.lifecycle.ports import PurgeContext, SourceSize, VolumeUsage
from hse_doc_studio.infra.lifecycle.files import CollabStateSource
from hse_doc_studio.use_cases.lifecycle.engine import ProcessCounters

NOW = datetime(2026, 11, 10, tzinfo=UTC)


def _ctx(cutoff: datetime | None, *, deadline: float | None = None) -> PurgeContext:
    return PurgeContext(now=NOW, cutoff=cutoff, batch_size=10, deadline=deadline or time.monotonic() + 30)


def _state(root: Path, project: str, name: str, age_days: float) -> Path:
    path = root / project / f"{name}.ystate"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * 100)
    stamp = (datetime.now(UTC) - timedelta(days=age_days)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


async def test__collab_state__removes_only_stale_files_and_empty_folders(tmp_path: Path) -> None:
    old = _state(tmp_path, "p1", "a", 200)
    fresh = _state(tmp_path, "p2", "b", 1)
    _state(tmp_path, "p3", "c", 300)
    foreign = tmp_path / "p1" / "keep.txt"
    foreign.write_text("не состояние")
    source = CollabStateSource(tmp_path)

    result = await source.purge(_ctx(datetime.now(UTC) - timedelta(days=90)))

    assert result.removed == 2
    assert not old.exists() and fresh.exists() and foreign.exists()
    assert not (tmp_path / "p3").exists()
    assert (await source.measure()).bytes == 100 + len("не состояние".encode())


async def test__collab_state__no_cutoff_or_missing_root__nothing(tmp_path: Path) -> None:
    stale = _state(tmp_path, "p1", "a", 500)

    assert (await CollabStateSource(tmp_path).purge(_ctx(None))).removed == 0
    assert stale.exists()
    assert (await CollabStateSource(tmp_path / "nope").purge(_ctx(NOW))).removed == 0
    assert (await CollabStateSource(tmp_path / "nope").measure()).bytes == 0


async def test__collab_state__budget_exhausted__reports_more(tmp_path: Path) -> None:
    _state(tmp_path, "p1", "a", 500)

    result = await CollabStateSource(tmp_path).purge(_ctx(NOW, deadline=time.monotonic() - 1))

    assert result.more and result.removed == 0


def test__collector__exposes_sources_volumes_and_safe_mode() -> None:
    counters = {
        "audit_log": ProcessCounters(
            removed=5, partitions_dropped=2, errors=1, last_run_ts=1_700_000_000.0, size=SourceSize(2048, 10, 4)
        ),
        "idle": ProcessCounters(),
    }
    volumes = [VolumeUsage("data", 900, 1000, 100), VolumeUsage("database", 5, None, None)]
    mode = SafeMode()
    mode.set(True, "data")

    text = "\n".join(lifecycle_collector(lambda: counters, lambda: volumes, mode)())

    assert 'hse_lifecycle_source_bytes{source="audit_log"} 2048' in text
    assert 'hse_lifecycle_source_rows{source="audit_log"} 10' in text
    assert 'hse_lifecycle_removed_total{source="audit_log"} 5' in text
    assert 'hse_lifecycle_partitions_dropped_total{source="audit_log"} 2' in text
    assert 'hse_lifecycle_errors_total{source="audit_log"} 1' in text
    assert 'hse_lifecycle_last_run_timestamp_seconds{source="audit_log"} 1700000000' in text
    assert 'hse_lifecycle_last_run_timestamp_seconds{source="idle"}' not in text
    assert 'hse_storage_used_ratio{volume="data"} 0.9' in text
    assert 'hse_storage_total_bytes{volume="database"}' not in text
    assert "hse_storage_safe_mode 1" in text
