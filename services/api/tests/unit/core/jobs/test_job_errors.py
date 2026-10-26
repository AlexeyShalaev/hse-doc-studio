from __future__ import annotations

import pytest
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.jobs.enums import JobErrorCategory
from hse_doc_studio.core.jobs.errors import JobError, JobFailedError, JobFailure, JobUnavailableError


@pytest.mark.parametrize(
    ("category", "exc_type"),
    [
        (JobErrorCategory.invalid_input, ValueError),
        (JobErrorCategory.not_found, NotFoundError),
        (JobErrorCategory.unavailable, JobUnavailableError),
        (JobErrorCategory.internal, JobFailedError),
    ],
)
def test__job_error__raise_for_error__category_maps_to_exception_type(
    category: JobErrorCategory, exc_type: type[Exception]
) -> None:
    with pytest.raises(exc_type) as info:
        JobError(category=category, code="some_code", detail="raw detail").raise_for_error()

    assert str(info.value) == "raw detail"
    assert type(info.value) is exc_type


def test__job_error__raise_for_error__empty_detail_falls_back_to_code() -> None:
    with pytest.raises(ValueError, match="unknown_signature_format"):
        JobError(category=JobErrorCategory.invalid_input, code="unknown_signature_format").raise_for_error()


def test__job_failure__carries_the_error_and_a_readable_message() -> None:
    failure = JobFailure.of(JobErrorCategory.unavailable, "gpg_unavailable", "no gpg")

    assert failure.error == JobError(JobErrorCategory.unavailable, "gpg_unavailable", "no gpg")
    assert str(failure) == "no gpg"
    assert str(JobFailure(JobError(JobErrorCategory.internal, "x"))) == "x"


def test__job_failed_and_unavailable__are_runtime_errors() -> None:
    assert issubclass(JobFailedError, RuntimeError)
    assert issubclass(JobUnavailableError, RuntimeError)
