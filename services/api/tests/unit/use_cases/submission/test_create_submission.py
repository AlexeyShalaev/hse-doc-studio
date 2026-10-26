from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import ExtraSubmissionItem, SubmissionDocItem
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.entities import JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError
from hse_doc_studio.core.jobs.files import ArtifactRef, IProjectFileProbe
from hse_doc_studio.core.jobs.office import (
    OfficeConvertPayload,
    OfficeConvertReason,
    OfficeConvertResult,
    OfficeConvertStatus,
)
from hse_doc_studio.core.jobs.pack import PackResult, PackSubmissionPayload
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.submission.create_submission import (
    CreateSubmissionInput,
    CreateSubmissionUC,
    _form_id_for_extra,
)
from hse_doc_studio.use_cases.submission.pack_planner import PackPlanner
from structlog.testing import capture_logs

from tests.factories import make_custom_file_override, make_document, make_project, make_template_version

# parents[0]=submission, [1]=use_cases, [2]=unit, [3]=tests, [4]=service-root, [5]=services, [6]=monorepo
_PACKS_DIR = Path(__file__).resolve().parents[6] / "packs"

_AI_SOURCE = ".hse-studio/forms/ai_declaration.json"


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
    """Запоминает задачи и пишет их в общий журнал событий вместе с сохранением записи и журнала."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.specs: list[JobSpec] = []
        self.result = JobResult(status=JobStatus.succeeded, data=OfficeConvertResult(status=OfficeConvertStatus.ok))
        self.pack_result: JobResult | None = None

    async def run(self, spec: JobSpec, *, timeout_s: float | None = None) -> JobResult:
        self.specs.append(spec)
        if isinstance(spec.payload, PackSubmissionPayload):
            self.events.append("pack")
            return self.pack_result or self._packed(spec.payload)
        assert isinstance(spec.payload, OfficeConvertPayload)
        self.events.append(f"convert:{spec.payload.source.path}")
        return self.result

    @staticmethod
    def _packed(payload: PackSubmissionPayload) -> JobResult:
        base = f"submissions/{payload.base_name}"
        return JobResult(
            status=JobStatus.succeeded,
            data=PackResult(
                archive=ArtifactRef(f"{base}.zip", "0" * 64, 10),
                folder=ArtifactRef(base, "1" * 64, 20),
            ),
        )


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
    def __init__(self, folder: Path, docs: list, files: set[str], planner: PackPlanner | None = None) -> None:
        self.events: list[str] = []
        self.dispatcher = FakeDispatcher(self.events)
        self.probes = FakeProbeFactory(files)
        self.project: Project = make_project(folder=folder, documents=docs)
        self.items = [SubmissionDocItem(doc_id=d.id, signatures=()) for d in docs]
        project_repo = MagicMock()
        project_repo.get.return_value = self.project
        project_repo.save.side_effect = lambda *_: self.events.append("remember")
        index = MagicMock()
        index.list_known.return_value = [folder]
        templates = MagicMock()
        templates.get_version.return_value = make_template_version()
        profiles = MagicMock()
        profiles.get_profile.return_value = MagicMock(extra_items=[])
        profiles.build_item_list.return_value = self.items
        signatures = MagicMock()
        self.submission_repo = MagicMock()
        self.submission_repo.save.side_effect = lambda *_: self.events.append("save")
        self.changelog_repo = MagicMock()
        self.changelog_repo.append.side_effect = lambda *_: self.events.append("changelog")
        self.uc = CreateSubmissionUC(
            project_repo=project_repo,
            project_index_repo=index,
            template_repo=templates,
            submission_repo=self.submission_repo,
            submission_profile_service=profiles,
            signature_repo=signatures,
            materializer=MagicMock(),
            planner=planner or PackPlanner(),
            key_exporter=MagicMock(),
            changelog_repo=self.changelog_repo,
            render_form_uc=MagicMock(),
            dispatcher=self.dispatcher,
            file_probes=self.probes,
        )

    @property
    def job_events(self) -> list[str]:
        """События до сохранения записи: конвертации и сама сборка."""
        return [e for e in self.events if e not in {"remember", "save", "changelog"}]

    async def create(self, decisions: dict[str, bool] | None):  # noqa: ANN202
        return await self.uc.execute(
            CreateSubmissionInput(
                project_id=self.project.id,
                profile_id="final",
                items=[],
                extra_items=[],
                custom_doc_decisions=decisions,
            )
        )


async def test__create_submission__custom_docx_decision_true__office_job_runs_before_packing(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".docx")], {"tz/_custom/tz.docx"})
    set_interface_language("en")

    await h.create({"tz": True})

    assert h.job_events == ["convert:tz/_custom/tz.docx", "pack"]
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
    assert set(h.probes.roots) == {tmp_path}


async def test__create_submission__preview_write_failed__logs_pdf_path_and_detail_as_before(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".docx")], {"tz/_custom/tz.docx"})
    h.dispatcher.result = JobResult(
        status=JobStatus.succeeded,
        data=OfficeConvertResult(
            status=OfficeConvertStatus.unavailable, reason_code="write_failed", detail="disk full"
        ),
    )

    with capture_logs() as logs:
        await h.create({"tz": True})

    event = next(e for e in logs if e["event"] == "assembler: custom doc preview write failed")
    assert event["path"] == str(tmp_path / "tz/_custom/tz.pdf")
    assert event["exc"] == "disk full"
    assert h.job_events == ["convert:tz/_custom/tz.docx", "pack"]


async def test__create_submission__remembered_decision__office_job_runs(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".docx", remembered=True)], {"tz/_custom/tz.docx"})

    await h.create(None)

    assert h.job_events == ["convert:tz/_custom/tz.docx", "pack"]


async def test__create_submission__sibling_exists__no_job(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".docx")], {"tz/_custom/tz.docx", "tz/_custom/tz.pdf"})

    await h.create({"tz": True})

    assert h.job_events == ["pack"]


@pytest.mark.parametrize(
    ("ext", "decisions"),
    [(".docx", {"tz": False}), (".docx", None), (".pdf", {"tz": True}), (".zip", {"tz": True})],
)
async def test__create_submission__decision_false_or_non_convertible__no_job(
    tmp_path, ext: str, decisions: dict[str, bool] | None
) -> None:
    h = Harness(tmp_path, [_doc("tz", ext)], {f"tz/_custom/tz{ext}"})

    await h.create(decisions)

    assert h.job_events == ["pack"]


async def test__create_submission__source_missing__no_job(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".docx")], set())

    await h.create({"tz": True})

    assert h.job_events == ["pack"]


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

    # Планировщик не найдет sibling и положит сырой файл: пакет не падает.
    assert h.job_events == ["convert:tz/_custom/tz.docx", "pack"]


async def test__create_submission__two_docs__converted_sequentially_in_item_order(tmp_path) -> None:
    docs = [_doc("b_doc", ".docx"), _doc("a_doc", ".pptx"), _doc("c_doc", ".docx")]
    h = Harness(tmp_path, docs, {f"{d.id}/_custom/{d.id}{d.custom_file.ext}" for d in docs})

    await h.create({"b_doc": True, "a_doc": True, "c_doc": False})

    assert h.job_events == ["convert:b_doc/_custom/b_doc.docx", "convert:a_doc/_custom/a_doc.pptx", "pack"]


async def test__create_submission__fake_dispatcher__payload_has_manifest_relative_paths_only(tmp_path) -> None:
    docs = [_doc("tz", ".pdf"), _doc("spec", ".docx")]
    h = Harness(tmp_path, docs, {"tz/_custom/tz.pdf", "spec/_custom/spec.docx"})

    out = await h.create({"spec": False})

    spec = h.dispatcher.specs[-1]
    assert spec.kind is JobKind.pack_submission
    assert spec.id == out.submission.id
    assert spec.tags == frozenset({"pack"})
    assert spec.project_id == h.project.id
    assert spec.local_root == tmp_path
    payload = spec.payload
    assert isinstance(payload, PackSubmissionPayload)
    assert payload.keep_folder is True
    assert payload.profile_id == "final"
    assert payload.base_name.startswith("final-")
    assert payload.base_name.endswith(spec.id.hex[:8])
    assert [e.arcname for e in payload.entries] == ["tz.pdf", "spec.docx"]
    paths = [f.path for f in payload.manifest_files()]
    assert paths == ["tz/_custom/tz.pdf", "spec/_custom/spec.docx"]
    assert all(not Path(path).is_absolute() and ".." not in Path(path).parts for path in paths)


async def test__create_submission__job_result__record_paths_are_absolute_under_project(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".pdf")], {"tz/_custom/tz.pdf"})

    out = await h.create(None)

    base = h.dispatcher.specs[-1].payload.base_name
    assert out.submission.output_path == tmp_path / "submissions" / f"{base}.zip"
    assert out.submission.output_dir == tmp_path / "submissions" / base
    assert h.submission_repo.save.call_args.args[0] is out.submission
    entry = h.changelog_repo.append.call_args.args[1]
    assert entry.summary == f"Pack submission created: profile=final, archive={base}.zip"


async def test__create_submission__job_invalid_input__value_error_and_no_record(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".pdf")], {"tz/_custom/tz.pdf"})
    h.dispatcher.pack_result = JobResult(
        status=JobStatus.failed,
        error=JobError(JobErrorCategory.invalid_input, "archive_failed", "Archive format '7z' requires a tool"),
    )

    with pytest.raises(ValueError, match="requires a tool"):
        await h.create({"tz": True})

    assert h.events == ["pack"]
    h.submission_repo.save.assert_not_called()
    h.changelog_repo.append.assert_not_called()


async def test__create_submission__planner_error__no_job_and_no_record(tmp_path) -> None:
    planner = MagicMock()
    planner.build.side_effect = ValueError("rebuilt after the PDF was frozen")
    h = Harness(tmp_path, [_doc("tz", ".pdf")], {"tz/_custom/tz.pdf"}, planner=planner)

    with pytest.raises(ValueError, match="rebuilt after"):
        await h.create(None)

    assert h.events == []
    h.submission_repo.save.assert_not_called()


async def test__create_submission__success__record_and_changelog_written_after_result_in_order(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".pdf")], {"tz/_custom/tz.pdf"})

    await h.create({"tz": True})

    assert h.events == ["pack", "remember", "save", "changelog"]


async def test__create_submission__agent_tool_without_actor__actor_local(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".pdf")], {"tz/_custom/tz.pdf"})
    set_current_actor(None)

    await h.create(None)

    assert h.dispatcher.specs[-1].actor == Actor.local()


async def test__create_submission__request_actor__passed_to_job(tmp_path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".pdf")], {"tz/_custom/tz.pdf"})
    actor = Actor.user("u1", "Ivan")
    set_current_actor(actor)
    try:
        await h.create(None)
    finally:
        set_current_actor(None)

    assert h.dispatcher.specs[-1].actor == actor


def test__form_id_for_extra__maps_form_answers_source_to_form_id() -> None:
    ai_extra = ExtraSubmissionItem(source=_AI_SOURCE, output_name="Декларация ИИ.md", format="markdown")
    repo = YamlTemplateRepository(_PACKS_DIR)
    repo.load()
    version = repo.get_version("hse-cs-se", "vkr", "2026.1")
    assert version is not None

    assert _form_id_for_extra(ai_extra, version) == "ai_declaration"
    # Non-form source → not rendered through a template.
    raw = ExtraSubmissionItem(source="some/other/file.json", output_name="x.md", format="markdown")
    assert _form_id_for_extra(raw, version) is None
    # Wrong format → ignored.
    not_md = ExtraSubmissionItem(source=_AI_SOURCE, output_name="x.txt", format="raw")
    assert _form_id_for_extra(not_md, version) is None
