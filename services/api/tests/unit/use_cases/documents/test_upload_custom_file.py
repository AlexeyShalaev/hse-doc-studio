from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.entities import JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.office import (
    OfficeConvertPayload,
    OfficeConvertReason,
    OfficeConvertResult,
    OfficeConvertStatus,
)
from hse_doc_studio.use_cases.documents.upload_custom_file import UploadCustomFileInput, UploadCustomFileUC
from structlog.testing import capture_logs

from tests.factories import make_document, make_document_definition, make_project, make_template_version

_PDF_REF = ArtifactRef(path="tz/_custom/ТЗ.pdf", sha256="0" * 64, size=3)


class FakeJobDispatcher:
    """Запоминает запущенные задачи и отвечает заранее заданным результатом."""

    def __init__(self) -> None:
        self.result = JobResult(
            status=JobStatus.succeeded, data=OfficeConvertResult(status=OfficeConvertStatus.ok, output=_PDF_REF)
        )
        self.run_specs: list[JobSpec] = []
        self.run_timeouts: list[float | None] = []

    async def run(self, spec: JobSpec, *, timeout_s: float | None = None) -> JobResult:
        self.run_specs.append(spec)
        self.run_timeouts.append(timeout_s)
        return self.result


class Harness:
    def __init__(self, folder) -> None:
        self.dispatcher = FakeJobDispatcher()
        self.project_repo = MagicMock()
        project_index_repo = MagicMock()
        project_index_repo.list_known.return_value = [folder]
        self.template_repo = MagicMock()
        self.template_repo.get_version.return_value = make_template_version(documents=(make_document_definition("tz"),))
        self.file_repo = MagicMock()
        self.signature_repo = MagicMock()
        self.signature_repo.get_state.return_value = MagicMock(placements={})
        vcs = MagicMock()
        vcs.is_available.return_value = False
        self.project: Project = make_project(folder=folder, documents=[make_document("tz")])
        self.project_repo.get.return_value = self.project
        self.uc = UploadCustomFileUC(
            project_repo=self.project_repo,
            project_index_repo=project_index_repo,
            template_repo=self.template_repo,
            file_repo=self.file_repo,
            signature_repo=self.signature_repo,
            dispatcher=self.dispatcher,
            vcs_service=vcs,
            vcs_locks=MagicMock(),
            vcs_throttle=MagicMock(),
        )

    async def upload(self, filename: str):
        return await self.uc.execute(
            UploadCustomFileInput(project_id=self.project.id, doc_id="tz", filename=filename, content=b"data")
        )


async def test__upload_custom_file__docx__submits_office_job_and_reports_generated(tmp_path) -> None:
    h = Harness(tmp_path)
    set_interface_language("en")

    out = await h.upload("ТЗ.docx")

    assert out.preview_generated is True
    assert len(h.dispatcher.run_specs) == 1
    spec = h.dispatcher.run_specs[0]
    assert spec.kind is JobKind.office_convert
    assert spec.tags == frozenset({"office"})
    assert spec.project_id == h.project.id
    assert spec.local_root == tmp_path
    assert spec.locale is Lang.en
    assert spec.actor == Actor.local()
    assert spec.payload == OfficeConvertPayload(
        source=spec.payload.source,
        output_path="tz/_custom/ТЗ.pdf",
        image=None,
        reason=OfficeConvertReason.upload,
    )
    assert spec.payload.source.path == "tz/_custom/ТЗ.docx"
    assert h.dispatcher.run_timeouts == [None]


async def test__upload_custom_file__current_actor__goes_to_the_job(tmp_path) -> None:
    h = Harness(tmp_path)
    actor = Actor.user("u1", name="Test")
    set_current_actor(actor)
    try:
        await h.upload("ТЗ.docx")
    finally:
        set_current_actor(None)

    assert h.dispatcher.run_specs[0].actor == actor


@pytest.mark.parametrize(
    "result",
    [
        JobResult(status=JobStatus.failed, error=JobError(JobErrorCategory.internal, "handler_crashed", "boom")),
        JobResult(status=JobStatus.timed_out, error=JobError(JobErrorCategory.internal, "timed_out", "")),
        JobResult(
            status=JobStatus.succeeded,
            data=OfficeConvertResult(status=OfficeConvertStatus.unavailable, reason_code="converter_unavailable"),
        ),
        JobResult(
            status=JobStatus.succeeded,
            data=OfficeConvertResult(
                status=OfficeConvertStatus.unavailable, reason_code="write_failed", detail="disk full"
            ),
        ),
    ],
    ids=["failed", "timed_out", "converter_unavailable", "write_failed"],
)
async def test__upload_custom_file__dispatcher_failed__flag_false_upload_ok(tmp_path, result: JobResult) -> None:
    h = Harness(tmp_path)
    h.dispatcher.result = result

    out = await h.upload("ТЗ.docx")

    assert out.preview_generated is False
    assert out.document.custom_file is not None
    assert out.document.custom_file.stored_path == "tz/_custom/ТЗ.docx"
    h.file_repo.write.assert_called_once()
    h.project_repo.save.assert_called_once()


@pytest.mark.parametrize("filename", ["ТЗ.pdf", "notes.txt", "scan.png"])
async def test__upload_custom_file__pdf_or_non_office_ext__no_job(tmp_path, filename: str) -> None:
    h = Harness(tmp_path)

    out = await h.upload(filename)

    assert out.preview_generated is False
    assert h.dispatcher.run_specs == []


async def test__upload_custom_file__backslash_in_name__upload_ok_without_preview(tmp_path) -> None:
    h = Harness(tmp_path)

    out = await h.upload("C:\\docs\\ТЗ.docx")

    assert out.preview_generated is False
    assert out.document.custom_file is not None
    assert h.dispatcher.run_specs == []
    h.file_repo.write.assert_called_once()
    h.project_repo.save.assert_called_once()


async def test__upload_custom_file__preview_write_failed__logs_pdf_path_and_detail_like_before(tmp_path) -> None:
    h = Harness(tmp_path)
    h.dispatcher.result = JobResult(
        status=JobStatus.succeeded,
        data=OfficeConvertResult(
            status=OfficeConvertStatus.unavailable, reason_code="write_failed", detail="disk full"
        ),
    )

    with capture_logs() as logs:
        await h.upload("ТЗ.docx")

    event = next(e for e in logs if e["event"] == "upload_custom_file: preview write failed")
    assert event["path"] == str(tmp_path / "tz/_custom/ТЗ.pdf")
    assert event["exc"] == "disk full"


async def test__upload_custom_file__conversion_job_failed__logs_error_detail_as_exc(tmp_path) -> None:
    h = Harness(tmp_path)
    h.dispatcher.result = JobResult(
        status=JobStatus.failed, error=JobError(JobErrorCategory.internal, "handler_crashed", "converter exploded")
    )

    with capture_logs() as logs:
        await h.upload("ТЗ.docx")

    event = next(e for e in logs if e["event"] == "upload_custom_file: preview conversion failed")
    assert event["path"] == "tz/_custom/ТЗ.docx"
    assert event["exc"] == "converter exploded"
