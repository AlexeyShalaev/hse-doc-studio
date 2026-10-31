"""Периоды, умолчания установки, разрешение предела и состояние использования."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.quotas import QuotaOverride, QuotaOwnerKind, QuotaResource
from hse_doc_studio.core.quotas.kinds import Period, QuotaKind, QuotaScope, period_end, period_start
from hse_doc_studio.core.quotas.policy import (
    LimitSource,
    OnExceed,
    OverrideIndex,
    QuotaPolicy,
    QuotaPolicyError,
    QuotaState,
    policy_from,
    resolve_org_limit,
    resolve_user_limit,
    state_of,
)


def test__period__day_and_month_boundaries_are_utc() -> None:
    now = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)

    assert period_start(Period.day, now) == date(2026, 12, 31)
    assert period_start(Period.month, now) == date(2026, 12, 1)
    assert period_end(Period.day, now) == datetime(2027, 1, 1, tzinfo=UTC)
    assert period_end(Period.month, now) == datetime(2027, 1, 1, tzinfo=UTC)
    assert period_start(Period.none, now) is None
    assert period_end(Period.none, now) is None


def test__period__month_end_for_february() -> None:
    assert period_end(Period.month, datetime(2027, 2, 10, tzinfo=UTC)) == datetime(2027, 3, 1, tzinfo=UTC)


def test__policy_from__reads_defaults_and_ignores_garbage() -> None:
    policy = policy_from(
        {
            "quota.storage.user": 1000,
            "quota.builds.org": 50,
            "quota.ai_tokens_day.user": True,
            "quota.members.user": "many",
            "quota.warn_percent": 70,
            "quota.on_exceed": "reject",
        }
    )

    assert policy.default(QuotaKind.storage, QuotaScope.user) == 1000
    assert policy.default(QuotaKind.builds, QuotaScope.org) == 50
    assert policy.default(QuotaKind.ai_tokens_day, QuotaScope.user) is None
    assert policy.default(QuotaKind.members, QuotaScope.user) is None
    assert policy.warn_percent == 70
    assert policy.on_exceed is OnExceed.reject


def test__policy_from__broken_mode_and_percent_fall_back_to_defaults() -> None:
    policy = policy_from({"quota.on_exceed": "explode", "quota.warn_percent": 500})

    assert policy.on_exceed is OnExceed.deprioritize
    assert policy.warn_percent == 80


def test__policy__rejects_out_of_range_percent() -> None:
    with pytest.raises(QuotaPolicyError):
        QuotaPolicy(warn_percent=0)


def test__resolve_user_limit__user_beats_org_beats_installation() -> None:
    user, member, org = uuid4(), uuid4(), uuid4()
    policy = QuotaPolicy(limits={(QuotaKind.builds, QuotaScope.user): 100})
    index = OverrideIndex.build(
        [
            QuotaOverride(QuotaOwnerKind.user, user.hex, QuotaResource.builds_user, 5),
            QuotaOverride(QuotaOwnerKind.org, str(org), QuotaResource.builds_user, 20),
        ]
    )

    own = resolve_user_limit(QuotaKind.builds, user, org, policy, index)
    via_org = resolve_user_limit(QuotaKind.builds, member, org, policy, index)
    default = resolve_user_limit(QuotaKind.builds, member, None, policy, index)

    assert (own.hard, own.source) == (5, LimitSource.user)  # type: ignore[union-attr]
    assert (via_org.hard, via_org.source) == (20, LimitSource.org)  # type: ignore[union-attr]
    assert (default.hard, default.source) == (100, LimitSource.installation)  # type: ignore[union-attr]
    assert resolve_user_limit(QuotaKind.storage, member, None, policy, index) is None


def test__resolve_org_limit__override_then_default() -> None:
    org, other = uuid4(), uuid4()
    policy = QuotaPolicy(limits={(QuotaKind.storage, QuotaScope.org): 7})
    index = OverrideIndex.build([QuotaOverride(QuotaOwnerKind.org, str(org), QuotaResource.storage_org, 9)])

    assert resolve_org_limit(QuotaKind.storage, org, policy, index).hard == 9  # type: ignore[union-attr]
    assert resolve_org_limit(QuotaKind.storage, other, policy, index).hard == 7  # type: ignore[union-attr]
    assert resolve_org_limit(QuotaKind.builds, other, policy, index) is None


@pytest.mark.parametrize(
    ("used", "limit", "expected"),
    [
        (0, None, QuotaState.unlimited),
        (79, 100, QuotaState.ok),
        (80, 100, QuotaState.warning),
        (99, 100, QuotaState.warning),
        (100, 100, QuotaState.exceeded),
        (150, 100, QuotaState.exceeded),
    ],
)
def test__state_of__thresholds(used: int, limit: int | None, expected: QuotaState) -> None:
    assert state_of(used, limit, 80) is expected
