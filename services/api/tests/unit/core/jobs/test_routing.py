from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass, JobState
from hse_doc_studio.core.jobs.queue import EnqueueRequest, QueuedJob
from hse_doc_studio.core.jobs.routing import (
    JobRoute,
    PersonalRunnerSettings,
    RouteDecision,
    RouteReason,
    RunnerScope,
    counts_against_installation,
    may_feed_shared_cache,
)
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind

NOW = datetime(2026, 10, 30, tzinfo=UTC)


def _job(scope: RunnerScope | None) -> QueuedJob:
    return QueuedJob(
        id=uuid4(),
        kind=JobKind.compile,
        project_id=uuid4(),
        user_id=uuid4(),
        org_id=None,
        tags=frozenset({"tex"}),
        priority_class=JobPriorityClass.interactive,
        vtime=1.0,
        queued_at=NOW,
        state=JobState.running,
        attempt=1,
        max_attempts=2,
        timeout_s=600.0,
        payload={},
        runner_scope=scope,
    )


def _request(**overrides: object) -> EnqueueRequest:
    fields: dict[str, object] = {
        "job_id": uuid4(),
        "kind": JobKind.compile,
        "project_id": uuid4(),
        "user_id": uuid4(),
        "tags": frozenset({"tex"}),
        "payload": {},
    }
    return EnqueueRequest(**{**fields, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("scope", "expected"), [(RunnerScope.shared, True), (RunnerScope.personal, False), (None, False)]
)
def test__may_feed_shared_cache__only_shared_runner_output(scope: RunnerScope | None, expected: bool) -> None:
    assert may_feed_shared_cache(_job(scope)) is expected
    assert counts_against_installation(_job(scope)) is expected


def test__enqueue_request__pinned_needs_a_target_runner() -> None:
    with pytest.raises(ValueError, match="pinned"):
        _request(route=JobRoute.pinned)
    with pytest.raises(ValueError, match="pinned"):
        _request(target_runner_id=uuid4())
    assert _request(route=JobRoute.pinned, target_runner_id=uuid4()).route is JobRoute.pinned


def test__enqueue_request__personal_first_needs_owner_and_window() -> None:
    with pytest.raises(ValueError, match="personal_first"):
        _request(route=JobRoute.personal_first, route_owner_id="u1")
    with pytest.raises(ValueError, match="personal_first"):
        _request(route_owner_id="u1", personal_until=NOW)
    request = _request(route=JobRoute.personal_first, route_owner_id="u1", personal_until=NOW)
    assert request.route_owner_id == "u1"


def test__route_decision__shared_carries_no_window() -> None:
    assert RouteDecision.shared(RouteReason.disabled) == RouteDecision(JobRoute.shared, RouteReason.disabled)
    with pytest.raises(ValueError, match="personal_first"):
        RouteDecision(JobRoute.personal_first, RouteReason.waiting_personal)


def test__personal_settings__ranges_are_enforced() -> None:
    assert PersonalRunnerSettings() == PersonalRunnerSettings(enabled=True, wait_s=5, max_per_user=5)
    with pytest.raises(ValueError, match="wait_s"):
        PersonalRunnerSettings(wait_s=61)
    with pytest.raises(ValueError, match="max_per_user"):
        PersonalRunnerSettings(max_per_user=0)


def test__runner__scope_follows_owner_kind() -> None:
    runner = Runner(
        id="r1",
        name="r",
        token_hash="h",
        tags=frozenset(),
        concurrency=1,
        resource_class="standard",
        version="1",
        created_at=NOW,
    )
    assert runner.scope is RunnerScope.shared
    assert replace(runner, owner_kind=RunnerOwnerKind.user, owner_id="u1").scope is RunnerScope.personal
