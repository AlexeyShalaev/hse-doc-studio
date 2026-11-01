from __future__ import annotations

import dataclasses
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.queue import EnqueueRequest, QueuedJob
from hse_doc_studio.core.jobs.relay import RelayEventKind, RelayMethod, RelayPath, is_relay_route
from hse_doc_studio.core.jobs.routing import JobRoute, RunnerScope, counts_against_installation, may_feed_shared_cache
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.core.jobs.wire import RelayEvent, RelayEventBatch

from tests.unit.core.jobs.samples import make_relay_payload


@pytest.mark.parametrize(
    ("method", "path", "allowed"),
    [
        ("GET", "models", True),
        ("POST", "chat/completions", True),
        ("POST", "embeddings", True),
        ("GET", "chat/completions", False),
        ("POST", "../admin", False),
        ("DELETE", "models", False),
    ],
)
def test__is_relay_route__only_the_whitelist(method: str, path: str, allowed: bool) -> None:
    assert is_relay_route(method, path) is allowed


def test__relay_payload__rejects_routes_outside_the_whitelist_and_bad_names() -> None:
    payload = make_relay_payload()
    with pytest.raises(ValueError, match="not allowed"):
        dataclasses.replace(payload, method=RelayMethod.get)
    with pytest.raises(ValueError, match="endpoint"):
        dataclasses.replace(payload, endpoint="Ollama/../x")
    with pytest.raises(ValueError, match="GET carries no body"):
        dataclasses.replace(payload, method=RelayMethod.get, path=RelayPath.models)


def test__relay_event__head_needs_status_data_needs_bytes_error_needs_code() -> None:
    with pytest.raises(ValueError, match="status"):
        RelayEvent(kind=RelayEventKind.head)
    with pytest.raises(ValueError, match="data"):
        RelayEvent(kind=RelayEventKind.data, data="")
    with pytest.raises(ValueError, match="code"):
        RelayEvent(kind=RelayEventKind.error)
    with pytest.raises(ValueError, match="1..64"):
        RelayEventBatch(attempt=1, seq=0, events=())


def test__enqueue_request__pinned_needs_a_target_and_only_pinned_has_one() -> None:
    base = {
        "job_id": uuid4(),
        "kind": JobKind.ai_relay,
        "project_id": uuid4(),
        "user_id": uuid4(),
        "tags": frozenset({"ai"}),
        "payload": {},
    }
    with pytest.raises(ValueError, match="pinned"):
        EnqueueRequest(**base, route=JobRoute.pinned)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="pinned"):
        EnqueueRequest(**base, target_runner_id=uuid4())  # type: ignore[arg-type]
    assert EnqueueRequest(**base, route=JobRoute.pinned, target_runner_id=uuid4()).route is JobRoute.pinned  # type: ignore[arg-type]


def test__shared_cache_and_quota__only_shared_scope_counts() -> None:
    job = QueuedJob(
        id=uuid4(),
        kind=JobKind.compile,
        project_id=uuid4(),
        user_id=uuid4(),
        org_id=None,
        tags=frozenset(),
        priority_class=0,  # type: ignore[arg-type]
        vtime=0.0,
        queued_at=None,  # type: ignore[arg-type]
        state="running",  # type: ignore[arg-type]
        attempt=1,
        max_attempts=1,
        timeout_s=1.0,
        payload={},
    )
    assert not may_feed_shared_cache(job)
    shared = dataclasses.replace(job, runner_scope=RunnerScope.shared)
    personal = dataclasses.replace(job, runner_scope=RunnerScope.personal)
    assert may_feed_shared_cache(shared)
    assert counts_against_installation(shared)
    assert not may_feed_shared_cache(personal)
    assert not counts_against_installation(personal)


def test__runner_scope__personal_for_a_user_runner() -> None:
    runner = Runner(
        id="r",
        name="r",
        token_hash="h",
        tags=frozenset(),
        concurrency=1,
        resource_class="standard",
        version="1",
        created_at=None,  # type: ignore[arg-type]
    )
    assert runner.scope is RunnerScope.shared
    assert dataclasses.replace(runner, owner_kind=RunnerOwnerKind.user, owner_id="u").scope is RunnerScope.personal
