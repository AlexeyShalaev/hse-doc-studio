from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from hse_doc_studio.api.observability.backup_metrics import backup_collector
from hse_doc_studio.core.backup.entities import BackupRun, RunStatus, RunTrigger
from hse_doc_studio.use_cases.backup.metrics import BackupMetricsRefresher, BackupMetricsState

from tests.fakes.backup import InMemoryRuns

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
MONITORING = Path(__file__).resolve().parents[5] / "deploy" / "monitoring"


def _run(run_id: str, status: RunStatus, *, hours_ago: float, size: int | None = None) -> BackupRun:
    started = NOW - timedelta(hours=hours_ago)
    return BackupRun(
        id=run_id,
        destination_id=None,
        destination_name="d",
        trigger=RunTrigger.manual,
        status=status,
        stage=None,
        started_at=started,
        finished_at=started + timedelta(seconds=90) if status is not RunStatus.running else None,
        size_bytes=size,
    )


class _Settings:
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    async def get_all(self) -> dict[str, object]:
        return {"backup.enabled": self._enabled}


def _values(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in lines:
        if not line.startswith("#"):
            name, _, value = line.rpartition(" ")
            out[name] = value
    return out


async def _snapshot(runs: list[BackupRun], *, enabled: bool = True) -> list[str]:
    repo = InMemoryRuns()
    for run in runs:
        repo.items[run.id] = run
    state = BackupMetricsState()
    await BackupMetricsRefresher(state, repo, _Settings(enabled)).refresh()  # type: ignore[arg-type]
    return list(backup_collector(state, clock=lambda: NOW)())


def test_not_loaded_state_exposes_nothing() -> None:
    assert list(backup_collector(BackupMetricsState())()) == []


@pytest.mark.asyncio
async def test_values_after_success_and_failure() -> None:
    lines = await _snapshot(
        [
            _run("1", RunStatus.ok, hours_ago=30, size=10),
            _run("2", RunStatus.ok, hours_ago=2, size=2048),
            _run("3", RunStatus.failed, hours_ago=1),
        ]
    )
    v = _values(lines)
    assert v["hse_backup_enabled"] == "1"
    assert v["hse_backup_running"] == "0"
    assert v["hse_backup_last_size_bytes"] == "2048"
    assert v["hse_backup_last_duration_seconds"] == "90.0"
    assert float(v["hse_backup_last_success_age_seconds"]) == pytest.approx(2 * 3600 - 90)
    assert v["hse_backup_failures_total"] == "1"
    assert v["hse_backup_last_run_ok"] == "0"
    assert v['hse_backup_runs_total{status="ok"}'] == "2"
    assert v['hse_backup_runs_total{status="failed"}'] == "1"
    assert v['hse_backup_runs_total{status="interrupted"}'] == "0"


@pytest.mark.asyncio
async def test_no_success_ever_gives_huge_age_and_running_flag() -> None:
    lines = await _snapshot([replace(_run("1", RunStatus.running, hours_ago=0.1), finished_at=None)], enabled=False)
    v = _values(lines)
    assert v["hse_backup_running"] == "1"
    assert v["hse_backup_enabled"] == "0"
    assert v["hse_backup_last_success_timestamp_seconds"] == "0.0"
    assert float(v["hse_backup_last_success_age_seconds"]) > 10**9
    assert "hse_backup_last_run_ok" not in v


def _exposed_names() -> set[str]:
    return {name.split("{")[0] for name in _values(_exposition())} | {
        m.group(1) for line in _exposition() if (m := re.match(r"# TYPE (\S+) ", line))
    }


def _exposition() -> list[str]:
    import asyncio

    runs = [_run("1", RunStatus.ok, hours_ago=2, size=1), _run("2", RunStatus.failed, hours_ago=1)]
    return asyncio.run(_snapshot(runs))


def test_alert_rules_reference_exposed_metrics() -> None:
    doc = yaml.safe_load((MONITORING / "backup-alerts.yml").read_text(encoding="utf-8"))
    rules = [r for g in doc["groups"] for r in g["rules"]]
    assert rules
    exposed = _exposed_names()
    for rule in rules:
        used = set(re.findall(r"hse_backup_[a-z_]+", rule["expr"]))
        assert used, rule["alert"]
        assert used <= exposed, (rule["alert"], used - exposed)


def test_dashboard_is_valid_and_uses_exposed_metrics() -> None:
    doc = json.loads((MONITORING / "backup-dashboard.json").read_text(encoding="utf-8"))
    exposed = _exposed_names()
    used = {m for p in doc["panels"] for t in p["targets"] for m in re.findall(r"hse_backup_[a-z_]+", t["expr"])}
    assert used
    assert used <= exposed
