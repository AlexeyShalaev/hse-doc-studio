from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass
from hse_doc_studio.core.jobs.scheduler import (
    AFFINITY_WAIT,
    FALLBACK_TIMEOUT_S,
    QueueQuota,
    advance_global_vtime,
    affinity_allows,
    assign_vtime,
    caps_allow,
    coalesce_key,
    max_attempts_of,
    priority_class_of,
    resolve_timeout,
    retry_available,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.unit
def test__assign_vtime__new_user__starts_at_global_time() -> None:
    assert assign_vtime(None, 10.0) == 11.0


@pytest.mark.unit
def test__assign_vtime__burst__grows_by_one_per_job() -> None:
    vtime, marks = None, []
    for _ in range(3):
        vtime = assign_vtime(vtime, 0.0)
        marks.append(vtime)
    assert marks == [1.0, 2.0, 3.0]


@pytest.mark.unit
def test__assign_vtime__idle_user_behind_global__does_not_keep_old_credit() -> None:
    assert assign_vtime(2.0, 50.0) == 51.0


@pytest.mark.unit
def test__assign_vtime__weight_shortens_step() -> None:
    assert assign_vtime(None, 0.0, cost=2.0, weight=4.0) == 0.5


@pytest.mark.unit
@pytest.mark.parametrize(("cost", "weight"), [(0.0, 1.0), (1.0, 0.0), (-1.0, 1.0)])
def test__assign_vtime__non_positive_cost_or_weight__raises(cost: float, weight: float) -> None:
    with pytest.raises(ValueError, match="positive"):
        assign_vtime(None, 0.0, cost, weight)


@pytest.mark.unit
def test__advance_global_vtime__never_goes_back() -> None:
    assert advance_global_vtime(5.0, 3.0) == 5.0
    assert advance_global_vtime(5.0, 8.0) == 8.0


@pytest.mark.unit
def test__coalesce_key__includes_project_kind_and_document() -> None:
    project = uuid4()
    assert coalesce_key(project, JobKind.compile, "main") == f"{project}:compile:main"


@pytest.mark.unit
def test__caps_allow__respects_user_and_org_limits() -> None:
    quota = QueueQuota(max_running_per_user=2, max_running_per_org=3)
    assert caps_allow(1, 2, quota)
    assert not caps_allow(2, 0, quota)
    assert not caps_allow(0, 3, quota)
    assert caps_allow(1, None, quota)
    assert caps_allow(100, 100, QueueQuota())


@pytest.mark.unit
def test__queue_quota__zero_limit__raises() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        QueueQuota(max_running_per_user=0)


@pytest.mark.unit
def test__resolve_timeout__uses_kind_default_and_quota_cap() -> None:
    assert resolve_timeout(JobKind.compile) == 600.0
    assert resolve_timeout(JobKind.compile, QueueQuota(max_timeout_s=60.0)) == 60.0
    assert resolve_timeout(JobKind.compile, QueueQuota(max_timeout_s=9000.0)) == 600.0
    assert FALLBACK_TIMEOUT_S > 0


@pytest.mark.unit
def test__priority_and_attempts__come_from_kind_policy() -> None:
    assert priority_class_of(JobKind.compile) is JobPriorityClass.interactive
    assert priority_class_of(JobKind.pack_submission) is JobPriorityClass.batch
    assert max_attempts_of(JobKind.compile) == 2


@pytest.mark.unit
def test__affinity_allows__own_or_unbound_job__always() -> None:
    runner = uuid4()
    assert affinity_allows(None, NOW, runner, NOW, affine_available=True)
    assert affinity_allows(runner, NOW, runner, NOW, affine_available=True)


@pytest.mark.unit
def test__affinity_allows__other_runner__waits_while_affine_is_available() -> None:
    affine, other = uuid4(), uuid4()
    assert not affinity_allows(affine, NOW, other, NOW + timedelta(seconds=1), affine_available=True)
    assert affinity_allows(affine, NOW, other, NOW + AFFINITY_WAIT, affine_available=True)
    assert affinity_allows(affine, NOW, other, NOW, affine_available=False)


@pytest.mark.unit
def test__retry_available__until_attempts_exhausted() -> None:
    assert retry_available(1, 2)
    assert not retry_available(2, 2)
