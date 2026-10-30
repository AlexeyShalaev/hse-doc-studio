"""Общие заготовки тестов ретрансляции ИИ."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass, JobState
from hse_doc_studio.core.jobs.queue import QueuedJob
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor
from hse_doc_studio.core.jobs.runners import DeclaredAiEndpoint, Runner, RunnerOwnerKind
from hse_doc_studio.core.jobs.wire import SERVER_FEATURES

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
OWNER_ID = "7a1d2c3b-4e5f-4a6b-8c7d-9e0f1a2b3c4d"


def make_queued_relay_job(*, state: JobState = JobState.running, error_code: str | None = None) -> QueuedJob:
    return QueuedJob(
        id=uuid4(),
        kind=JobKind.ai_relay,
        project_id=UUID(int=0),
        user_id=UUID(OWNER_ID),
        org_id=None,
        tags=frozenset({"ai"}),
        priority_class=JobPriorityClass.interactive,
        vtime=0.0,
        queued_at=NOW,
        state=state,
        attempt=1,
        max_attempts=1,
        timeout_s=900.0,
        payload={},
        error_code=error_code,
    )


def make_personal_runner(runner_id: str | None = None, *, owner_id: str = OWNER_ID, **changes: object) -> Runner:
    runner = Runner(
        id=runner_id or uuid4().hex,
        name="MacBook Анны",
        token_hash="h",
        tags=frozenset({"ai", "pack"}),
        concurrency=1,
        resource_class="standard",
        version="0.3.0",
        created_at=NOW,
        last_seen_at=NOW,
        owner_kind=RunnerOwnerKind.user,
        owner_id=owner_id,
        features=SERVER_FEATURES,
        ai_endpoints=(DeclaredAiEndpoint("ollama", AiEndpointFlavor.ollama),),
        ai_concurrency=2,
    )
    return replace(runner, **changes)  # type: ignore[arg-type]
