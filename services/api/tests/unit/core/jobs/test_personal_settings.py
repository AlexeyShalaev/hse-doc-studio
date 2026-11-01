from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.identity.instance_settings import (
    KEY_PERSONAL_ENABLED,
    KEY_PERSONAL_MAX_PER_USER,
    KEY_PERSONAL_WAIT_S,
    InstanceEnvOverrides,
    effective_personal_runner_settings,
)
from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.routing import PersonalRunnerSettings
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.use_cases.jobs.personal_settings import InstancePersonalRunnerSettings

NOW = datetime(2026, 10, 30, tzinfo=UTC)


def test__personal_settings__defaults_and_stored_values() -> None:
    assert effective_personal_runner_settings({}, InstanceEnvOverrides()) == PersonalRunnerSettings()
    stored = {KEY_PERSONAL_ENABLED: False, KEY_PERSONAL_WAIT_S: 0, KEY_PERSONAL_MAX_PER_USER: 3}
    assert effective_personal_runner_settings(stored, InstanceEnvOverrides()) == PersonalRunnerSettings(False, 0, 3)


def test__personal_settings__env_wins_even_with_false_and_zero() -> None:
    env = InstanceEnvOverrides(personal_runners_enabled=False, personal_runner_wait_s=0)
    stored = {KEY_PERSONAL_ENABLED: True, KEY_PERSONAL_WAIT_S: 30}
    assert effective_personal_runner_settings(stored, env) == PersonalRunnerSettings(False, 0, 5)
    assert {KEY_PERSONAL_ENABLED, KEY_PERSONAL_WAIT_S} <= env.locked_keys()


def test__personal_settings__out_of_range_stored_value_falls_back() -> None:
    stored = {KEY_PERSONAL_WAIT_S: 600, KEY_PERSONAL_MAX_PER_USER: 0, KEY_PERSONAL_ENABLED: "yes"}
    assert effective_personal_runner_settings(stored, InstanceEnvOverrides()) == PersonalRunnerSettings()


class _Repo:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.reads = 0

    async def get_all(self) -> dict[str, object]:
        self.reads += 1
        return dict(self.values)


async def test__instance_personal_settings__caches_until_invalidated() -> None:
    repo, ticks = _Repo(), [0.0]
    service = InstancePersonalRunnerSettings(repo, InstanceEnvOverrides(), monotonic=lambda: ticks[0])  # type: ignore[arg-type]
    await service.current()
    repo.values[KEY_PERSONAL_ENABLED] = False
    assert (await service.current()).enabled is True
    service.invalidate()
    assert (await service.current()).enabled is False
    assert repo.reads == 2


def _runner(**changes: object) -> Runner:
    runner = Runner(
        id="r",
        name="r",
        token_hash="h",
        tags=frozenset(),
        concurrency=1,
        resource_class="standard",
        version="1",
        created_at=NOW,
        last_seen_at=NOW - timedelta(seconds=10),
        owner_kind=RunnerOwnerKind.user,
        owner_id="u",
    )
    return replace(runner, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "enabled", "expected"),
    [
        ({}, True, RunnerStatus.online),
        ({}, False, RunnerStatus.disabled),
        ({"revoked_at": NOW}, False, RunnerStatus.revoked),
        ({"paused": True}, True, RunnerStatus.paused),
        ({"offline_at": NOW - timedelta(seconds=5)}, True, RunnerStatus.offline),
        ({"offline_at": NOW - timedelta(seconds=20)}, True, RunnerStatus.online),
        ({"owner_kind": RunnerOwnerKind.instance, "owner_id": None}, False, RunnerStatus.online),
    ],
    ids=["online", "disabled", "revoked_first", "paused", "said_offline", "polled_after_offline", "shared_unaffected"],
)
def test__runner_status__personal_states(changes: dict[str, object], enabled: bool, expected: RunnerStatus) -> None:
    assert runner_status(_runner(**changes), NOW, personal_enabled=enabled) is expected
