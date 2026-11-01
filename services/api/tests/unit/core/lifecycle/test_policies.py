"""Реестр политик: границы, защита аудита, расчёт эффективного срока."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.lifecycle.disk import (
    KEY_CRITICAL_PERCENT,
    KEY_WARN_PERCENT,
    SafeMode,
    StorageLevel,
    StorageThresholds,
    effective_thresholds,
)
from hse_doc_studio.core.lifecycle.policies import (
    POLICIES,
    POLICY_BY_KEY,
    Strategy,
    effective_days,
)

AUDIT = POLICY_BY_KEY["audit_log"]
JOBS = POLICY_BY_KEY["jobs"]


def test__registry__keys_unique_and_bounds_consistent() -> None:
    assert len({p.key for p in POLICIES}) == len(POLICIES)
    for p in POLICIES:
        if p.bounds is not None:
            assert p.bounds.min_days <= p.bounds.default_days <= p.bounds.max_days, p.key


def test__audit__protected_with_floor_and_no_manual_run() -> None:
    assert AUDIT.protected
    assert not AUDIT.run_now
    assert AUDIT.bounds is not None
    assert AUDIT.bounds.min_days >= 90
    assert AUDIT.strategy is Strategy.partition_drop


def test__editable__only_engine_strategies_with_bounds() -> None:
    for p in POLICIES:
        if p.editable:
            assert p.bounds is not None
            assert p.strategy in {Strategy.partition_drop, Strategy.delete_batches, Strategy.file_sweep}
        else:
            assert p.strategy not in {Strategy.partition_drop} or p.bounds is None


def test__effective_days__admin_value_within_bounds__wins() -> None:
    assert effective_days(AUDIT, {AUDIT.setting_key: 400}, default_days=365) == 400


@pytest.mark.parametrize("bad", [1, 89, 10_000, True, "30", None])
def test__effective_days__admin_value_out_of_bounds__falls_back_to_default(bad: object) -> None:
    assert effective_days(AUDIT, {AUDIT.setting_key: bad}, default_days=365) == 365


def test__effective_days__env_zero__means_keep_forever() -> None:
    assert effective_days(AUDIT, {}, default_days=0) is None


def test__effective_days__env_default_is_clamped_into_bounds() -> None:
    assert effective_days(AUDIT, {}, default_days=7) == AUDIT.bounds.min_days  # type: ignore[union-attr]
    assert effective_days(JOBS, {}, default_days=100_000) == JOBS.bounds.max_days  # type: ignore[union-attr]


def test__effective_days__no_env_no_admin__registry_default() -> None:
    assert effective_days(JOBS, {}) == JOBS.bounds.default_days  # type: ignore[union-attr]


def test__effective_days__fixed_policy__none() -> None:
    assert effective_days(POLICY_BY_KEY["guest_sessions"], {}) is None


@pytest.mark.parametrize(
    ("ratio", "level"),
    [
        (None, StorageLevel.ok),
        (0.5, StorageLevel.ok),
        (0.8, StorageLevel.warning),
        (0.89, StorageLevel.warning),
        (0.9, StorageLevel.critical),
        (1.2, StorageLevel.critical),
    ],
)
def test__thresholds__levels(ratio: float | None, level: StorageLevel) -> None:
    assert StorageThresholds().level(ratio) is level


def test__effective_thresholds__admin_pair_in_bounds() -> None:
    got = effective_thresholds({KEY_WARN_PERCENT: 70, KEY_CRITICAL_PERCENT: 85})
    assert (got.warn_percent, got.critical_percent) == (70, 85)


@pytest.mark.parametrize(
    "stored",
    [
        {KEY_WARN_PERCENT: 90, KEY_CRITICAL_PERCENT: 80},
        {KEY_WARN_PERCENT: 10},
        {KEY_CRITICAL_PERCENT: 100},
        {KEY_WARN_PERCENT: "x"},
    ],
)
def test__effective_thresholds__broken_pair__defaults(stored: dict[str, object]) -> None:
    assert effective_thresholds(stored) == StorageThresholds()


def test__safe_mode__reason_cleared_on_off() -> None:
    mode = SafeMode()
    mode.set(True, "data")
    assert (mode.active, mode.reason) == (True, "data")
    mode.set(False, "ignored")
    assert (mode.active, mode.reason) == (False, None)
