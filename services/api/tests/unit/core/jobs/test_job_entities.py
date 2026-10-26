from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hse_doc_studio.core.jobs.entities import (
    BuildOutcome,
    CheckPlan,
    CompileResult,
    JobResult,
    compile_job_tags,
    job_tags,
)
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError, JobFailedError

from tests.unit.core.jobs.samples import make_compile_payload, make_compile_result, make_compile_spec


@pytest.mark.parametrize(
    ("needs_compile", "source_ext", "expected"),
    [
        (True, ".tex", {"tex"}),
        (False, ".pptx", {"office"}),
        (False, ".DOCX", {"office"}),
        (False, ".pdf", set()),
        (False, ".zip", set()),
        (False, "", set()),
    ],
)
def test__compile_job_tags__latexmk_office_copy_and_pdf_custom(
    needs_compile: bool, source_ext: str, expected: set[str]
) -> None:
    assert compile_job_tags(needs_compile, source_ext) == frozenset(expected)


def test__job_tags__compile_payload__derived_from_source_extension() -> None:
    assert job_tags(JobKind.compile, make_compile_payload()) == frozenset({"tex"})
    assert job_tags(JobKind.compile, make_compile_payload(needs_compile=False, source_file="tz/_custom/ТЗ.docx")) == {
        "office"
    }
    assert (
        job_tags(JobKind.compile, make_compile_payload(needs_compile=False, source_file="tz/_custom/ТЗ.pdf")) == set()
    )


def test__job_spec__is_frozen_and_payload_round_trips_asdict() -> None:
    spec = make_compile_spec(local_root=Path("/projects/a"))

    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.kind = JobKind.compile  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.payload.doc_id = "x"  # type: ignore[attr-defined]

    as_dict = dataclasses.asdict(spec.payload)
    assert as_dict["check_plan"]["needs_languagetool"] is True
    assert as_dict["check_plan"]["ignored_rule_ids"] == {"lt:TYPO", "gost/other"}
    rebuilt = dataclasses.replace(spec.payload, check_plan=CheckPlan(**as_dict["check_plan"]))
    assert rebuilt.doc_id == spec.payload.doc_id
    assert rebuilt.check_plan.needs_languagetool is True


def test__compile_result__carries_the_build_phase_fields() -> None:
    result = make_compile_result().data_as(CompileResult)
    assert result.build_ok
    assert (result.pages, result.words, result.chars) == (7, 1200, 9000)
    assert result.finished_at == datetime(2026, 10, 26, 9, 30, 15, 123456, tzinfo=timezone.utc)


def test__build_outcome__optional_counts_default_to_none() -> None:
    outcome = BuildOutcome(success=True, status=JobStatus.succeeded, finished_at=datetime.now(tz=timezone.utc))
    assert (outcome.pages, outcome.words, outcome.chars) == (None, None, None)


def test__job_result__data_as_wrong_or_missing_data__raises() -> None:
    class _Other(CompileResult):
        pass

    result = make_compile_result()
    assert result.data_as(CompileResult) is result.data
    with pytest.raises(JobFailedError):
        result.data_as(_Other)
    with pytest.raises(JobFailedError):
        JobResult(status=JobStatus.failed).data_as(CompileResult)


def test__job_result__raise_for_error__only_when_error_present() -> None:
    JobResult(status=JobStatus.succeeded).raise_for_error()
    failed = JobResult(status=JobStatus.failed, error=JobError(category=JobErrorCategory.internal, code="boom"))
    with pytest.raises(JobFailedError, match="boom"):
        failed.raise_for_error()
