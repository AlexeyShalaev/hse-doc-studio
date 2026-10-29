"""Приоритет user > org > установка для квот задач."""

from __future__ import annotations

from uuid import uuid4

from hse_doc_studio.core.jobs.quotas import (
    QuotaOverride,
    QuotaOwnerKind,
    QuotaResource,
    duration_cap,
    org_key,
    overrides_to_queue_quota,
)
from hse_doc_studio.core.jobs.scheduler import QueueQuota


def test__org_key__uuid_string_is_kept_and_slug_is_stable() -> None:
    org = uuid4()

    assert org_key(str(org)) == org
    assert org_key("hse-fkn") == org_key("hse-fkn")
    assert org_key("hse-fkn") != org_key("hse-other")


def test__overrides_to_queue_quota__splits_by_owner_and_resource() -> None:
    user, org = uuid4(), uuid4()
    quota = overrides_to_queue_quota(
        QueueQuota(max_running_per_user=4),
        [
            QuotaOverride(QuotaOwnerKind.user, str(user), QuotaResource.concurrent_user, 1),
            QuotaOverride(QuotaOwnerKind.org, str(org), QuotaResource.concurrent_user, 2),
            QuotaOverride(QuotaOwnerKind.org, str(org), QuotaResource.concurrent_org, 6),
            QuotaOverride(QuotaOwnerKind.user, "not-a-uuid", QuotaResource.concurrent_user, 9),
            QuotaOverride(QuotaOwnerKind.user, str(user), QuotaResource.max_duration_s, 30),
        ],
    )

    assert quota.max_running_per_user == 4
    assert quota.user_caps == {user: 1}
    assert quota.org_user_caps == {org: 2}
    assert quota.org_caps == {org: 6}


def test__duration_cap__user_beats_org_beats_default() -> None:
    user, member, org = uuid4(), uuid4(), uuid4()
    overrides = [
        QuotaOverride(QuotaOwnerKind.user, str(user), QuotaResource.max_duration_s, 60),
        QuotaOverride(QuotaOwnerKind.org, str(org), QuotaResource.max_duration_s, 120),
    ]

    assert duration_cap(300, overrides, user, org) == 60
    assert duration_cap(300, overrides, member, org) == 120
    assert duration_cap(300, overrides, member, uuid4()) == 300
    assert duration_cap(None, overrides, member, None) is None
