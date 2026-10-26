from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.entities import JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError
from hse_doc_studio.core.jobs.files import ArtifactRef, ManifestFile
from hse_doc_studio.core.jobs.office import (
    REASON_CONVERTER_UNAVAILABLE,
    REASON_WRITE_FAILED,
    OfficeConvertPayload,
    OfficeConvertReason,
    OfficeConvertResult,
    OfficeConvertStatus,
)
from hse_doc_studio.use_cases.office_editor.preview_observer import PreviewRefreshObserver
from structlog.testing import capture_logs


def _spec(root: Path) -> JobSpec:
    payload = OfficeConvertPayload(
        source=ManifestFile("pres/pptx/presentation.pptx"),
        output_path="pres/pptx/presentation.pdf",
        image="img:1",
        reason=OfficeConvertReason.save_refresh,
    )
    return JobSpec(
        id=uuid4(),
        kind=JobKind.office_convert,
        tags=frozenset({"office"}),
        project_id=uuid4(),
        actor=Actor.local(),
        locale=Lang.ru,
        payload=payload,
        local_root=root,
    )


def _ok() -> JobResult:
    ref = ArtifactRef(path="pres/pptx/presentation.pdf", sha256="0" * 64, size=3)
    return JobResult(
        status=JobStatus.succeeded, data=OfficeConvertResult(status=OfficeConvertStatus.ok, output=ref), error=None
    )


def _unavailable(reason: str, detail: str = "") -> JobResult:
    data = OfficeConvertResult(status=OfficeConvertStatus.unavailable, reason_code=reason, detail=detail)
    return JobResult(status=JobStatus.succeeded, data=data, error=None)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("result", "event", "level"),
    [
        (_ok(), "office-editor: preview refreshed", "info"),
        (_unavailable(REASON_CONVERTER_UNAVAILABLE), "office-editor: preview refresh skipped", "info"),
        (_unavailable(REASON_WRITE_FAILED, "disk full"), "office-editor: preview refresh failed", "warning"),
        (
            JobResult(
                status=JobStatus.failed,
                data=None,
                error=JobError(JobErrorCategory.internal, "handler_crashed", "boom"),
            ),
            "office-editor: preview refresh failed",
            "warning",
        ),
        (
            JobResult(status=JobStatus.cancelled, data=None, error=None),
            "office-editor: preview refresh failed",
            "warning",
        ),
    ],
)
async def test__preview_observer__logs_outcome(tmp_path: Path, result: JobResult, event: str, level: str) -> None:
    with capture_logs() as logs:
        await PreviewRefreshObserver().on_finished(_spec(tmp_path), result)

    assert len(logs) == 1
    assert logs[0]["event"] == event
    assert logs[0]["log_level"] == level
    expected = "presentation.pdf" if event.endswith("refreshed") else "presentation.pptx"
    assert str(logs[0]["path"]).startswith(str(tmp_path))
    assert str(logs[0]["path"]).endswith(expected)
