from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.access.entities import Actor, ActorKind, Role
from hse_doc_studio.core.jobs.codec import (
    decode_envelope,
    decode_poll_response,
    encode_envelope,
    encode_poll_response,
)
from hse_doc_studio.core.jobs.entities import JobSpec
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass, JobState, JobStatus
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.jobs.policy import JobKindPolicy
from hse_doc_studio.core.jobs.registry import build_job_kinds
from hse_doc_studio.core.jobs.wire import (
    HeartbeatResponse,
    JobEnvelope,
    PollRequest,
    PollResponse,
    RunnerRegisterRequest,
)

from tests.unit.core.jobs.samples import (
    make_compile_spec,
    make_office_spec,
    make_pack_spec,
    make_relay_spec,
    make_verify_spec,
)

_SPECS = {
    JobKind.compile: make_compile_spec,
    JobKind.office_convert: make_office_spec,
    JobKind.verify_detached: make_verify_spec,
    JobKind.pack_submission: make_pack_spec,
    JobKind.ai_relay: make_relay_spec,
}
_MANIFEST = (ManifestFile("tz/main.tex", "a" * 64, 10), ManifestFile("common/meta.tex", "b" * 64, 3))


def _envelope(spec: JobSpec, **overrides: Any) -> JobEnvelope:
    fields: dict[str, Any] = {
        "spec": spec,
        "manifest": _MANIFEST,
        "timeout_s": 600.0,
        "attempt": 1,
        "job_token": "token",
        "actor_role": Role.editor,
    }
    return JobEnvelope(**{**fields, **overrides})


def test__envelope__every_kind_has_a_sample() -> None:
    assert set(_SPECS) == {spec.kind for spec in build_job_kinds()}


@pytest.mark.parametrize("kind", list(_SPECS), ids=lambda kind: kind.value)
def test__envelope__round_trips_every_kind_through_json(kind: JobKind) -> None:
    envelope = _envelope(_SPECS[kind]())
    wire = json.loads(json.dumps(encode_envelope(envelope)))
    assert decode_envelope(wire) == envelope


@pytest.mark.parametrize("kind", list(_SPECS), ids=lambda kind: kind.value)
def test__poll_response__round_trips_with_and_without_a_job(kind: JobKind) -> None:
    full = PollResponse(_envelope(_SPECS[kind]()))
    assert decode_poll_response(json.loads(json.dumps(encode_poll_response(full)))) == full
    assert decode_poll_response(encode_poll_response(PollResponse())) == PollResponse()


def test__envelope__carries_the_actor_snapshot_and_role() -> None:
    actor = Actor(kind=ActorKind.user, id="u-1", name="Анна", email="a@x.io")
    spec = dataclasses.replace(make_compile_spec(), actor=actor)
    decoded = decode_envelope(encode_envelope(_envelope(spec, actor_role=Role.reviewer)))
    assert decoded.spec.actor == actor
    assert decoded.actor_role is Role.reviewer


def test__envelope__without_a_role_stays_null() -> None:
    wire = encode_envelope(_envelope(make_compile_spec(), actor_role=None))
    assert wire["actor_role"] is None
    assert decode_envelope(wire).actor_role is None


def test__envelope__rejects_a_path_in_the_spec() -> None:
    spec = make_compile_spec(local_root=Path("/srv/projects/x"))
    with pytest.raises(ValueError, match="local_root"):
        _envelope(spec)


def test__envelope__rejects_bytes_in_the_wire_payload() -> None:
    with pytest.raises(TypeError, match="cannot be sent"):
        encode_envelope(_envelope(make_compile_spec(), job_token=b"x"))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [{"attempt": 0}, {"timeout_s": 0.0}, {"job_token": ""}, {"manifest": (ManifestFile("a.tex"),)}],
    ids=["attempt", "timeout", "token", "manifest_without_hash"],
)
def test__envelope__rejects_invalid_fields(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"."):
        _envelope(make_compile_spec(), **overrides)


def test__decode_envelope__rejects_unknown_fields() -> None:
    wire = encode_envelope(_envelope(make_compile_spec()))
    with pytest.raises(ValueError, match="unknown envelope fields"):
        decode_envelope({**wire, "extra": 1})


def test__decode_envelope__rejects_a_missing_field() -> None:
    wire = encode_envelope(_envelope(make_compile_spec()))
    del wire["job_token"]
    with pytest.raises(KeyError):
        decode_envelope(wire)


def test__poll_request__limits_the_wait() -> None:
    PollRequest(wait_s=25)
    with pytest.raises(ValueError, match="wait_s"):
        PollRequest(wait_s=26)


def test__register_request__needs_a_slot() -> None:
    with pytest.raises(ValueError, match="concurrency"):
        RunnerRegisterRequest("r", 1, "1", frozenset(), 0)


def test__heartbeat_response__keeps_the_lease_deadline() -> None:
    response = HeartbeatResponse(cancel=False, lease_until=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert response.lease_until.tzinfo is not None


def test__job_state__terminal_states_mirror_job_status() -> None:
    assert {JobState.of_status(status) for status in JobStatus} == {state for state in JobState if state.is_terminal}
    assert not JobState.queued.is_terminal
    assert not JobState.running.is_terminal


def test__registry__every_kind_has_a_server_queue_policy() -> None:
    # Ретрансляция ИИ не повторяется: часть ответа модели уже ушла клиенту.
    for spec in (spec for spec in build_job_kinds() if spec.kind is not JobKind.ai_relay):
        policy = spec.policy
        assert isinstance(policy.priority_class, JobPriorityClass)
        # Ретрансляция ИИ не повторяется: ответ модели уже ушёл потребителю.
        assert policy.retryable is (spec.kind is not JobKind.ai_relay)
        assert policy.max_attempts == (1 if spec.kind is JobKind.ai_relay else 2)
        assert policy.default_timeout_s is not None
        assert policy.default_timeout_s > 0


def test__registry__compile_is_interactive_and_pack_is_batch() -> None:
    by_kind = {spec.kind: spec.policy for spec in build_job_kinds()}
    assert by_kind[JobKind.compile].priority_class is JobPriorityClass.interactive
    assert by_kind[JobKind.pack_submission].priority_class is JobPriorityClass.batch
    assert by_kind[JobKind.compile].default_timeout_s == 600.0


def test__policy__a_non_retryable_kind_has_one_attempt() -> None:
    with pytest.raises(ValueError, match="one attempt"):
        JobKindPolicy(retryable=False, max_attempts=2)
    with pytest.raises(ValueError, match="at least 1"):
        JobKindPolicy(max_attempts=0)
