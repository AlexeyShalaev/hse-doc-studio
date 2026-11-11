from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.codec import decode, encode
from hse_doc_studio.core.jobs.disk import (
    COMMAND_OPEN_STATES,
    COMMAND_TRANSITIONS,
    MAX_STEP_ERROR,
    CommandProgress,
    CommandStep,
    CommandStepKind,
    CommandStepStatus,
    DataVolume,
    DiskCleanupPayload,
    DiskMeasurePayload,
    DiskTarget,
    DockerDisk,
    RunnerCommand,
    RunnerCommandKind,
    RunnerCommandState,
    RunnerDiskReport,
    can_transition,
)
from hse_doc_studio.core.jobs.wire import CommandProgressRequest, RunnerCommandEnvelope

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "runner" / "fixtures"
_NOW = datetime(2026, 11, 11, 9, 30, tzinfo=UTC)
S = RunnerCommandState


def _report(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / "RunnerDiskReportBody" / f"{name}.json").read_text(encoding="utf-8"))


def test__states__finished_and_open_split_every_state() -> None:
    finished = {state for state in S if state.finished}
    assert finished == {S.done, S.cancelled, S.error, S.expired, S.lost}
    assert set(COMMAND_OPEN_STATES) == set(S) - finished
    assert set(COMMAND_TRANSITIONS) == set(S)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.queued, S.delivered),
        (S.queued, S.expired),
        (S.queued, S.cancelled),
        (S.delivered, S.running),
        (S.delivered, S.done),
        (S.delivered, S.lost),
        (S.running, S.running),
        (S.running, S.cancelling),
        (S.running, S.error),
        (S.cancelling, S.cancelled),
        (S.cancelling, S.done),
        (S.cancelling, S.lost),
    ],
)
def test__transitions__allowed(current: RunnerCommandState, target: RunnerCommandState) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.queued, S.running),
        (S.queued, S.lost),
        (S.cancelling, S.running),
        (S.done, S.running),
        (S.expired, S.delivered),
        (S.lost, S.done),
    ],
)
def test__transitions__refused(current: RunnerCommandState, target: RunnerCommandState) -> None:
    assert not can_transition(current, target)


def test__states__runner_reports_only_running_and_results() -> None:
    assert {state for state in S if state.reportable} == {S.running, S.done, S.cancelled, S.error}
    with pytest.raises(ValueError, match="report"):
        CommandProgressRequest(state=S.cancelling, progress=CommandProgress(steps=(), freed_bytes=0, error=None))


def test__payload__must_match_the_command_kind() -> None:
    cleanup = DiskCleanupPayload(targets=(DiskTarget.build_cache,))
    with pytest.raises(ValueError, match="does not take"):
        RunnerCommandEnvelope(id=uuid4(), kind=RunnerCommandKind.disk_measure, payload=cleanup, issued_at=_NOW)
    with pytest.raises(ValueError, match="does not take"):
        RunnerCommand(
            id=uuid4(),
            runner_id="r1",
            kind=RunnerCommandKind.disk_cleanup,
            payload=DiskMeasurePayload(),
            state=S.queued,
            created_by="u1",
            created_at=_NOW,
            updated_at=_NOW,
        )


def test__payload__round_trips_through_the_codec() -> None:
    for payload, kind in (
        (DiskMeasurePayload(), RunnerCommandKind.disk_measure),
        (DiskCleanupPayload(targets=(DiskTarget.old_versions,), include_rollback=True), RunnerCommandKind.disk_cleanup),
    ):
        envelope = RunnerCommandEnvelope(id=uuid4(), kind=kind, payload=payload, issued_at=_NOW)
        assert decode(RunnerCommandEnvelope, encode(envelope)) == envelope


@pytest.mark.parametrize(
    ("targets", "rollback", "message"),
    [
        ((), False, "at least one"),
        ((DiskTarget.build_cache, DiskTarget.build_cache), False, "unique"),
        ((DiskTarget.build_cache,), True, "old_versions"),
    ],
)
def test__cleanup_payload__rejects_bad_targets(targets: tuple[DiskTarget, ...], rollback: bool, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        DiskCleanupPayload(targets=targets, include_rollback=rollback)


def test__targets__only_runner_cache_works_without_docker() -> None:
    assert [target for target in DiskTarget if not target.needs_docker] == [DiskTarget.runner_cache]


def test__step__ref_only_on_images_and_containers_and_short_error() -> None:
    CommandStep(CommandStepKind.image, "texlive/texlive:TL2023-historic", CommandStepStatus.done, 1, None)
    with pytest.raises(ValueError, match="ref"):
        CommandStep(CommandStepKind.build_cache, "x", CommandStepStatus.pending, 0, None)
    with pytest.raises(ValueError, match="ref"):
        CommandStep(CommandStepKind.container, None, CommandStepStatus.pending, 0, None)
    with pytest.raises(ValueError, match="error"):
        CommandStep(CommandStepKind.runner_blobs, None, CommandStepStatus.error, 0, "e" * (MAX_STEP_ERROR + 1))


def test__report__unavailable_docker_reports_nothing() -> None:
    body = _report("docker")
    with pytest.raises(ValueError, match="unavailable"):
        decode(DockerDisk, {**body["docker"], "available": False})
    unavailable = decode(RunnerDiskReport, _report("docker_unavailable"))
    assert unavailable.docker is not None
    assert not unavailable.docker.available
    assert unavailable.targets == (DiskTarget.runner_cache,)


def test__report__volume_free_cannot_exceed_total() -> None:
    with pytest.raises(ValueError, match="free_bytes"):
        DataVolume(total_bytes=1, free_bytes=2)


def test__report__negative_sizes_are_rejected() -> None:
    body = _report("kubernetes")
    body["cache"]["blobs"]["bytes"] = -1
    with pytest.raises(ValueError, match="negative"):
        decode(RunnerDiskReport, body)
