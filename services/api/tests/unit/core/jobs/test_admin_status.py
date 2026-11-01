"""Статус раннера по последнему опросу и проверка значений квот."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.quotas import QuotaSettings, QuotaValueError, quota_settings_from
from hse_doc_studio.core.jobs.runners import Runner

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def _runner(**kwargs: object) -> Runner:
    base = Runner(
        id="r1",
        name="r",
        token_hash="h",
        tags=frozenset({"tex"}),
        concurrency=1,
        resource_class="standard",
        version="0.3.0",
        created_at=NOW - timedelta(days=1),
        last_seen_at=NOW,
    )
    return replace(base, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("silence_s", "expected"),
    [
        (0, RunnerStatus.online),
        (60, RunnerStatus.online),
        (61, RunnerStatus.stale),
        (300, RunnerStatus.stale),
        (301, RunnerStatus.offline),
    ],
)
def test__runner_status__by_last_seen(silence_s: int, expected: RunnerStatus) -> None:
    runner = _runner(last_seen_at=NOW - timedelta(seconds=silence_s))

    assert runner_status(runner, NOW) is expected


def test__runner_status__never_seen__offline() -> None:
    assert runner_status(_runner(last_seen_at=None), NOW) is RunnerStatus.offline


def test__runner_status__paused_and_revoked_win_over_freshness() -> None:
    assert runner_status(_runner(paused=True), NOW) is RunnerStatus.paused
    assert runner_status(_runner(paused=True, revoked_at=NOW), NOW) is RunnerStatus.revoked


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"user_concurrent": 0}, "user_concurrent"),
        ({"org_concurrent": 1001}, "org_concurrent"),
        ({"max_duration_s": 9}, "max_duration_s"),
        ({"max_duration_s": 86401}, "max_duration_s"),
    ],
)
def test__quota_settings__out_of_range__names_the_field(kwargs: dict[str, int], field: str) -> None:
    with pytest.raises(QuotaValueError) as exc:
        QuotaSettings(**kwargs)

    assert exc.value.field == field


def test__quota_settings_from__garbage__reads_as_unlimited() -> None:
    values = {"jobs.concurrent": "many", "jobs.max_duration_s": 5, "jobs.org_concurrent": True}

    assert quota_settings_from(values) == QuotaSettings()


def test__quota_settings__to_queue_quota__maps_limits() -> None:
    quota = QuotaSettings(user_concurrent=2, org_concurrent=5, max_duration_s=120).to_queue_quota()

    assert (quota.max_running_per_user, quota.max_running_per_org, quota.max_timeout_s) == (2, 5, 120.0)
