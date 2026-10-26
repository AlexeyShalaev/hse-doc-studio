from __future__ import annotations

import dataclasses
import json

import pytest
from hse_doc_studio.core.jobs.base import JobPayload, JobResultData
from hse_doc_studio.core.jobs.codec import decode_result, decode_spec, encode_result, encode_spec
from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.registry import build_job_kinds, job_kind_spec

from tests.unit.core.jobs.samples import (
    make_compile_payload,
    make_compile_result,
    make_compile_spec,
    make_office_payload,
    make_office_result,
    make_office_spec,
)

# Образцы для каждого вида: новый вид нельзя добавить, не дописав образец сюда.
_SAMPLE_SPECS = {JobKind.compile: make_compile_spec, JobKind.office_convert: make_office_spec}
_SAMPLE_RESULTS = {JobKind.compile: make_compile_result, JobKind.office_convert: make_office_result}
_SAMPLE_PAYLOADS = {JobKind.compile: make_compile_payload, JobKind.office_convert: make_office_payload}


def test__registry__every_job_kind_has_exactly_one_spec() -> None:
    kinds = [spec.kind for spec in build_job_kinds()]

    assert sorted(kinds) == sorted(JobKind)


@pytest.mark.parametrize("kind", list(JobKind))
def test__registry__spec_classes_subclass_the_marker_bases_and_are_frozen(kind: JobKind) -> None:
    spec = job_kind_spec(kind)

    assert issubclass(spec.payload_cls, JobPayload)
    assert issubclass(spec.result_cls, JobResultData)
    assert dataclasses.is_dataclass(spec.payload_cls)
    assert spec.payload_cls.__dataclass_params__.frozen  # type: ignore[attr-defined]
    assert spec.result_cls.__dataclass_params__.frozen  # type: ignore[attr-defined]


@pytest.mark.parametrize("kind", list(JobKind))
def test__registry__sample_spec_and_result_round_trip(kind: JobKind) -> None:
    spec = _SAMPLE_SPECS[kind]()
    result: JobResult = _SAMPLE_RESULTS[kind]()

    assert isinstance(spec.payload, job_kind_spec(kind).payload_cls)
    assert isinstance(result.data, job_kind_spec(kind).result_cls)
    assert decode_spec(json.loads(json.dumps(encode_spec(spec)))) == spec
    assert decode_result(kind, json.loads(json.dumps(encode_result(result)))) == result
    assert type(_SAMPLE_PAYLOADS[kind]()) is job_kind_spec(kind).payload_cls


def test__registry__compile_policy__streams_log_is_active_and_blocks_folder_ops() -> None:
    policy = job_kind_spec(JobKind.compile).policy

    assert (policy.streams_log, policy.counts_as_active, policy.blocks_folder_ops) == (True, True, True)
    assert not policy.awaitable
    assert not policy.detachable
    assert policy.embedded_concurrency is None
    assert policy.default_timeout_s is None


def test__registry__office_convert_policy__awaitable_detachable_idempotent_not_counted() -> None:
    policy = job_kind_spec(JobKind.office_convert).policy

    assert (policy.awaitable, policy.detachable, policy.idempotent) == (True, True, True)
    assert (policy.streams_log, policy.counts_as_active, policy.blocks_folder_ops) == (False, False, False)
    assert policy.embedded_concurrency is None


def test__registry__unregistered_kind__rejected() -> None:
    with pytest.raises(ValueError, match="unregistered"):
        job_kind_spec("nope")  # type: ignore[arg-type]


def test__job_status__values_are_the_four_terminal_outcomes() -> None:
    assert {s.value for s in JobStatus} == {"succeeded", "failed", "cancelled", "timed_out"}
