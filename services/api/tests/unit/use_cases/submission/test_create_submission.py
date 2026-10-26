from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import SubmissionDocItem
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.entities import JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError
from hse_doc_studio.core.jobs.files import IProjectFileProbe
from hse_doc_studio.core.jobs.office import (
    OfficeConvertPayload,
    OfficeConvertReason,
    OfficeConvertResult,
    OfficeConvertStatus,
)
from hse_doc_studio.use_cases.submission.create_submission import CreateSubmissionInput, CreateSubmissionUC

from tests.factories import make_custom_file_override, make_document, make_project, make_template_version


class FakeProbe:
    def __init__(self, files: set[str]) -> None:
        self._files = files

    def is_file(self, path: str) -> bool:
        return path in self._files


class FakeProbeFactory:
    def __init__(self, files: set[str]) -> None:
        self.files = files
        self.roots: list[Path] = []

    def for_root(self, root: Path) -> IProjectFileProbe:
        self.roots.append(root)
        return FakeProbe(self.files)  # type: ignore[return-value]


class FakeDispatcher:
    """Запоминает задачи и пишет их в общий журнал событий вместе с вызовом ассемблера."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.specs: list[JobSpec] = []
        self.result = JobResult(status=JobStatus.succeeded, data=OfficeConvertResult(status=OfficeConvertStatus.ok))

    async def run(self, spec: JobSpec, *, timeout_s: float | None = None) -> JobResult:
        assert isinstance(spec.payload, OfficeConvertPayload)
        self.specs.append(spec)
        self.events.append(f"convert:{spec.payload.source.path}")
        return self.result


def _doc(doc_id: str, ext: str, *, remembered: bool | None = None):  # noqa: ANN202
    return make_document(
        doc_id,
        custom_file=make_custom_file_override(
            original_filename=f"{doc_id}{ext}",
            stored_path=f"{doc_id}/_custom/{doc_id}{ext}",
            ext=ext,
            convert_to_pdf_at_package=remembered,
        ),
    )


class Harness:
    def __init__(self, folder: Path, docs: list, files: set[str]) -> None:
        self.events: list[str] = []
        self.dispatcher = FakeDispatcher(self.events)
        self.probes = FakeProbeFactory(files)
        self.project: Project = make_project(folder=folder, documents=docs)
        self.items = [SubmissionDocItem(doc_id=d.id, signatures=()) for d in docs]
        project_repo = MagicMock()
        project_repo.get.return_value = self.project
        index = MagicMock()
        index.list_known.return_value = [folder]
        templates = MagicMock()
        templates.get_version.return_value = make_template_version()
        profiles = MagicMock()
        profiles.get_profile.return_value = MagicMock(extra_items=[])
        profiles.build_item_list.return_value = self.items
        signatures = MagicMock()
        self.assembler = MagicMock()

        async def populate_dir(**_: object) -> list[str]:
            self.events.append("populate_dir")
            return []

        self.assembler.populate_dir = AsyncMock(side_effect=populate_dir)
        self.assembler.create_archive.return_value = folder / "submissions" / "a.zip"
        self.uc = CreateSubmissionUC(
            project_repo=project_repo,
            project_index_repo=index,
            template_repo=templates,
            submission_repo=MagicMock(),
            submission_profile_service=profiles,
            signature_repo=signatures,
            assembler=self.assembler,
            changelog_repo=MagicMock(),
            render_form_uc=MagicMock(),
            dispatcher=self.dispatcher,
            file_probes=self.probes,
        )

    async def create(self, decisions: dict[str, bool] | None) -> None:
        await self.uc.execute(
            CreateSubmissionInput(
                project_id=self.project.id,
                profile_id="final",
                items=[],
                extra_items=[],
                custom_doc_decisions=decisions,
            )
        )


async def test__create_submission__custom_docx_decision_true__office_job_runs_before_assembling(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".docx")], {"tz/_custom/tz.docx"})
    set_interface_language("en")

    await h.create({"tz": True})

    assert h.events == ["convert:tz/_custom/tz.docx", "populate_dir"]
    spec = h.dispatcher.specs[0]
    assert spec.kind is JobKind.office_convert
    assert spec.tags == frozenset({"office"})
    assert spec.project_id == h.project.id
    assert spec.local_root == tmp_path
    assert spec.locale is Lang.en
    assert spec.actor == Actor.local()
    assert spec.payload == OfficeConvertPayload(
        source=spec.payload.source,
        output_path="tz/_custom/tz.pdf",
        image=None,
        reason=OfficeConvertReason.package,
    )
    assert h.probes.roots == [tmp_path]


async def test__create_submission__remembered_decision__office_job_runs(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".docx", remembered=True)], {"tz/_custom/tz.docx"})

    await h.create(None)

    assert h.events == ["convert:tz/_custom/tz.docx", "populate_dir"]


async def test__create_submission__sibling_exists__no_job(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".docx")], {"tz/_custom/tz.docx", "tz/_custom/tz.pdf"})

    await h.create({"tz": True})

    assert h.events == ["populate_dir"]


@pytest.mark.parametrize(
    ("ext", "decisions"),
    [(".docx", {"tz": False}), (".docx", None), (".pdf", {"tz": True}), (".zip", {"tz": True})],
)
async def test__create_submission__decision_false_or_non_convertible__no_job(
    tmp_path, ext: str, decisions: dict[str, bool] | None
) -> None:
    h = Harness(tmp_path, [_doc("tz", ext)], {f"tz/_custom/tz{ext}"})

    await h.create(decisions)

    assert h.events == ["populate_dir"]


async def test__create_submission__source_missing__no_job(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".docx")], set())

    await h.create({"tz": True})

    assert h.events == ["populate_dir"]


@pytest.mark.parametrize(
    "result",
    [
        JobResult(status=JobStatus.failed, error=JobError(JobErrorCategory.internal, "handler_crashed", "boom")),
        JobResult(status=JobStatus.timed_out, error=JobError(JobErrorCategory.internal, "timed_out", "")),
        JobResult(
            status=JobStatus.succeeded,
            data=OfficeConvertResult(status=OfficeConvertStatus.unavailable, reason_code="converter_unavailable"),
        ),
    ],
    ids=["failed", "timed_out", "unavailable"],
)
async def test__create_submission__office_job_unavailable__package_still_built(tmp_path, result: JobResult) -> None:
    h = Harness(tmp_path, [_doc("tz", ".docx")], {"tz/_custom/tz.docx"})
    h.dispatcher.result = result

    await h.create({"tz": True})

    # Ассемблер не найдет sibling и положит сырой файл: пакет не падает.
    assert h.events == ["convert:tz/_custom/tz.docx", "populate_dir"]
    h.assembler.create_archive.assert_called_once()


async def test__create_submission__two_docs__converted_sequentially_in_item_order(tmp_path) -> None:
    docs = [_doc("b_doc", ".docx"), _doc("a_doc", ".pptx"), _doc("c_doc", ".docx")]
    h = Harness(tmp_path, docs, {f"{d.id}/_custom/{d.id}{d.custom_file.ext}" for d in docs})

    await h.create({"b_doc": True, "a_doc": True, "c_doc": False})

    assert h.events == ["convert:b_doc/_custom/b_doc.docx", "convert:a_doc/_custom/a_doc.pptx", "populate_dir"]
