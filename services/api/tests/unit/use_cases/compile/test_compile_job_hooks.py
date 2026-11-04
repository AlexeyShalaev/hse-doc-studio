"""CompileJobHooks: запись «идёт» и итог сборки, статус документа, журнал, VCS и архив PDF."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import ChangeLogKind, CheckSeverity, CompileStatus, DocumentStatus, EngineType
from hse_doc_studio.core.jobs.artifacts import PdfFingerprint
from hse_doc_studio.core.jobs.entities import CompileResult, JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError
from hse_doc_studio.core.value_objects import CheckResult
from hse_doc_studio.use_cases.compile.compile_hooks_factory import CompileJobHooksFactory
from hse_doc_studio.use_cases.compile.compile_job_hooks import CompileJobHooks

from tests.factories import make_document, make_project
from tests.unit.core.jobs.samples import JOB_ID, PROJECT_ID, make_compile_spec

STARTED_AT = datetime(2026, 10, 26, 9, 0, tzinfo=timezone.utc)
FINISHED_AT = datetime(2026, 10, 26, 9, 5, tzinfo=timezone.utc)


def _check(severity: CheckSeverity) -> CheckResult:
    return CheckResult(rule_id=f"rule/{severity}", severity=severity, message="m")


def _record(folder: Path) -> CompileRecord:
    return CompileRecord(
        id=JOB_ID,
        project_folder=folder,
        doc_id="tz",
        engine=EngineType.xelatex,
        status=CompileStatus.pending,
        started_at=STARTED_AT,
        finished_at=None,
        log="old",
        output_path=None,
        check_results=[],
        pages=None,
    )


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.folder = tmp_path
        self.events: list[str] = []
        self.compile_repo = AsyncMock()
        self.compile_repo.get_for_project.return_value = _record(tmp_path)
        self.project = make_project(folder=tmp_path, documents=[make_document("tz"), make_document("other")])
        self.project_repo = MagicMock()
        self.project_repo.get.return_value = self.project
        self.changelog_repo = MagicMock()
        self.vcs_service = MagicMock()
        self.vcs_service.is_available.return_value = True
        self.vcs_service.is_initialized.return_value = True
        self.vcs_service.commit.side_effect = lambda *a, **kw: self.events.append("vcs")
        self.vcs_locks = MagicMock()
        self.vcs_locks.for_folder.side_effect = lambda folder: self._lock()
        self.artifacts = AsyncMock()
        self.artifacts.archive_pdf.side_effect = lambda *a: self.events.append("archive")
        self.hooks = CompileJobHooks(
            compile_repo=self.compile_repo,
            project_repo=self.project_repo,
            changelog_repo=self.changelog_repo,
            template_repo=MagicMock(),
            vcs_service=self.vcs_service,
            vcs_locks=self.vcs_locks,
            artifacts=self.artifacts,
            project_folder=tmp_path,
        )

    @asynccontextmanager
    async def _lock(self) -> Any:
        yield

    @property
    def spec(self) -> JobSpec:
        return make_compile_spec(local_root=self.folder)

    @property
    def saved(self) -> list[CompileRecord]:
        return [call.args[0] for call in self.compile_repo.save.call_args_list]

    @property
    def doc_status(self) -> DocumentStatus | None:
        if not self.project_repo.save.called:
            return None
        saved = self.project_repo.save.call_args.args[0]
        return next(d.status for d in saved.documents if d.id == "tz")


def _result(status: JobStatus, *checks: CheckResult, with_data: bool = True) -> JobResult:
    data = (
        CompileResult(
            build_ok=status is JobStatus.succeeded,
            check_results=checks,
            pages=7,
            words=100,
            chars=500,
            finished_at=FINISHED_AT,
        )
        if with_data
        else None
    )
    return JobResult(status=status, data=data)


# --- on_started ---


async def test__on_started__record_exists__saved_as_running_with_empty_log(tmp_path: Path) -> None:
    env = Env(tmp_path)

    assert await env.hooks.on_started(env.spec) is True

    env.compile_repo.get_for_project.assert_called_once_with(tmp_path, JOB_ID)
    running = env.saved[0]
    assert (running.status, running.log, running.finished_at, running.started_at) == (
        CompileStatus.running,
        "",
        None,
        STARTED_AT,
    )
    assert (running.id, running.doc_id, running.engine) == (JOB_ID, "tz", EngineType.xelatex)


async def test__on_started__record_missing__returns_false_and_saves_nothing(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.compile_repo.get_for_project.return_value = None

    assert await env.hooks.on_started(env.spec) is False

    env.compile_repo.save.assert_not_called()


# --- on_finished: таблица статусов ---


@pytest.mark.parametrize(
    ("status", "checks", "record_status", "doc_status", "kind", "summary"),
    [
        (
            JobStatus.succeeded,
            (),
            CompileStatus.success,
            DocumentStatus.ok,
            ChangeLogKind.compile_ok,
            "Compile succeeded for tz",
        ),
        (
            JobStatus.succeeded,
            (_check(CheckSeverity.warn),),
            CompileStatus.success,
            DocumentStatus.warn,
            ChangeLogKind.compile_ok,
            "Compile succeeded for tz",
        ),
        (
            JobStatus.succeeded,
            (_check(CheckSeverity.info),),
            CompileStatus.success,
            DocumentStatus.ok,
            ChangeLogKind.compile_ok,
            "Compile succeeded for tz",
        ),
        (
            JobStatus.succeeded,
            (_check(CheckSeverity.warn), _check(CheckSeverity.err)),
            CompileStatus.success,
            DocumentStatus.err,
            ChangeLogKind.compile_ok,
            "Compile succeeded for tz",
        ),
        (
            JobStatus.failed,
            (),
            CompileStatus.failure,
            DocumentStatus.err,
            ChangeLogKind.compile_fail,
            "Compile failed for tz",
        ),
        (
            JobStatus.failed,
            (_check(CheckSeverity.warn),),
            CompileStatus.failure,
            DocumentStatus.err,
            ChangeLogKind.compile_fail,
            "Compile failed for tz",
        ),
        (
            JobStatus.cancelled,
            (),
            CompileStatus.cancelled,
            DocumentStatus.err,
            ChangeLogKind.compile_fail,
            "Compile cancelled for tz",
        ),
    ],
)
async def test__on_finished__status_table__record_document_and_changelog(
    tmp_path: Path,
    status: JobStatus,
    checks: tuple[CheckResult, ...],
    record_status: CompileStatus,
    doc_status: DocumentStatus,
    kind: ChangeLogKind,
    summary: str,
) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(status, *checks), "full log")

    final = env.saved[-1]
    assert final.status is record_status
    assert final.log.startswith("full log")
    assert (final.started_at, final.finished_at) == (STARTED_AT, FINISHED_AT)
    assert (final.pages, final.words, final.chars, final.output_path) == (7, 100, 500, None)
    assert final.check_results == list(checks)
    assert env.doc_status is doc_status
    saved_project = env.project_repo.save.call_args.args[0]
    assert next(d for d in saved_project.documents if d.id == "tz").last_compile_id == JOB_ID
    assert next(d for d in saved_project.documents if d.id == "other").status is not doc_status
    folder, entry = env.changelog_repo.append.call_args.args
    assert folder == tmp_path
    assert (entry.kind, entry.summary, entry.doc_id, entry.at, entry.note) == (kind, summary, "tz", FINISHED_AT, None)


async def test__on_finished__crash_result_without_data__failure_without_checks_and_pages(tmp_path: Path) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.failed, with_data=False), "[error] compile task crashed: x")

    final = env.saved[-1]
    assert final.status is CompileStatus.failure
    assert (final.check_results, final.pages, final.words, final.chars) == ([], None, None, None)
    assert final.finished_at is not None
    assert env.doc_status is DocumentStatus.err


# --- устойчивость к сбоям ---


async def test__on_finished__project_update_fails__swallowed_and_changelog_still_written(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.project_repo.get.side_effect = [RuntimeError("disk"), env.project]
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    env.changelog_repo.append.assert_called_once()
    env.artifacts.archive_pdf.assert_called_once()


async def test__on_finished__changelog_fails__swallowed_and_vcs_still_runs(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.changelog_repo.append.side_effect = RuntimeError("readonly")
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    assert env.events == ["vcs", "archive"]


async def test__on_finished__vcs_fails__swallowed_and_pdf_still_archived(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.vcs_service.commit.side_effect = RuntimeError("git broke")
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    env.artifacts.archive_pdf.assert_called_once()


async def test__on_finished__final_record_save_fails__propagates(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.compile_repo.save.side_effect = [None, OSError("no space")]
    await env.hooks.on_started(env.spec)

    with pytest.raises(OSError, match="no space"):
        await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    env.changelog_repo.append.assert_not_called()


# --- VCS и архив ---


async def test__on_finished__success__vcs_commit_then_archive_in_that_order(tmp_path: Path) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    assert env.events == ["vcs", "archive"]
    env.artifacts.archive_pdf.assert_called_once_with(PROJECT_ID, tmp_path, "tz", JOB_ID, "tz/main.tex")
    commit = env.vcs_service.commit.call_args
    assert commit.kwargs["message"] == "Сборка: tz · 7 стр."
    assert commit.kwargs["include_pdf"] is False


@pytest.mark.parametrize("status", [JobStatus.failed, JobStatus.cancelled])
async def test__on_finished__not_success__no_vcs_and_no_archive(tmp_path: Path, status: JobStatus) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(status), "log")

    assert env.events == []
    env.vcs_service.commit.assert_not_called()
    env.artifacts.archive_pdf.assert_not_called()


async def test__on_finished__auto_commit_disabled__no_vcs_but_archive(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.project.meta["vcs"] = {"auto_commit_on_compile": False}
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    assert env.events == ["archive"]


async def test__on_finished__vcs_unavailable__no_commit(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.vcs_service.is_available.return_value = False
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    assert env.events == ["archive"]


async def test__on_finished__vcs_not_initialized__initialized_before_commit_with_excludes(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.vcs_service.is_initialized.return_value = False
    env.project.meta["vcs"] = {"track_pdf": True}
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    env.vcs_service.init.assert_called_once()
    assert env.vcs_service.commit.call_args.kwargs["include_pdf"] is True


async def test__on_finished__no_pages__commit_message_without_page_count(tmp_path: Path) -> None:
    env = Env(tmp_path)
    result = JobResult(
        status=JobStatus.succeeded,
        data=CompileResult(build_ok=True, finished_at=FINISHED_AT),
    )
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, result, "log")

    assert env.vcs_service.commit.call_args.kwargs["message"] == "Сборка: tz"


async def test__on_finished__not_a_compile_spec__raises_type_error(tmp_path: Path) -> None:
    env = Env(tmp_path)
    spec = replace(env.spec, kind=JobKind.office_convert)

    with pytest.raises(TypeError):
        await env.hooks.on_finished(spec, _result(JobStatus.succeeded), "log")


# --- заменённая сборка и хуки после рестарта ---


async def test__on_finished__superseded__record_closed_but_document_state_belongs_to_newer_build(
    tmp_path: Path,
) -> None:
    env = Env(tmp_path)
    superseded = JobResult(status=JobStatus.cancelled, error=JobError(JobErrorCategory.internal, "superseded"))

    await env.hooks.on_finished(env.spec, superseded, "")

    assert env.saved[-1].status is CompileStatus.cancelled
    assert env.doc_status is None
    env.changelog_repo.append.assert_not_called()


async def test__on_finished__hooks_rebuilt_after_restart__started_at_comes_from_the_record(tmp_path: Path) -> None:
    env = Env(tmp_path)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "")

    assert env.saved[-1].started_at == STARTED_AT


def test__factory__compile_spec__builds_hooks_for_the_spec_folder(tmp_path: Path) -> None:
    env = Env(tmp_path)
    factory = CompileJobHooksFactory(
        env.compile_repo,
        env.project_repo,
        env.changelog_repo,
        MagicMock(),
        env.vcs_service,
        env.vcs_locks,
        env.artifacts,
    )

    assert factory.for_spec(env.spec) is not None
    assert factory.for_spec(replace(env.spec, local_root=None)) is None
    assert factory.for_spec(replace(env.spec, kind=JobKind.office_convert)) is None


# --- хуки после рестарта ---


async def test__recovered_hooks__finished_record__outcome_is_not_applied_twice(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.compile_repo.get_for_project.return_value = replace(_record(tmp_path), status=CompileStatus.success)
    hooks = CompileJobHooksFactory(
        env.compile_repo,
        env.project_repo,
        env.changelog_repo,
        MagicMock(),
        env.vcs_service,
        env.vcs_locks,
        env.artifacts,
    ).for_spec(env.spec)
    assert hooks is not None

    await hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    env.compile_repo.save.assert_not_called()
    env.changelog_repo.append.assert_not_called()
    env.artifacts.archive_pdf.assert_not_called()


async def test__recovered_hooks__record_missing__nothing_is_recreated(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.compile_repo.get_for_project.return_value = None
    hooks = CompileJobHooksFactory(
        env.compile_repo,
        env.project_repo,
        env.changelog_repo,
        MagicMock(),
        env.vcs_service,
        env.vcs_locks,
        env.artifacts,
    ).for_spec(env.spec)
    assert hooks is not None

    await hooks.on_finished(env.spec, _result(JobStatus.failed), "log")

    env.compile_repo.save.assert_not_called()


# --- коммит и отпечаток PDF в записи сборки (docs/design/connected-devices.md, часть 3) ---


async def test__on_finished__success__record_gets_commit_and_pdf_fingerprint(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.vcs_service.commit.side_effect = None
    env.vcs_service.commit.return_value = SimpleNamespace(id="c" * 40)
    env.artifacts.fingerprint_pdf.return_value = PdfFingerprint(size=1234, sha256="ab" * 32)
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    stamped = env.saved[-1]
    assert (stamped.source_commit, stamped.output_sha256, stamped.output_size) == ("c" * 40, "ab" * 32, 1234)
    assert stamped.status is CompileStatus.success


async def test__on_finished__nothing_to_commit_and_clean_tree__record_gets_current_head(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.vcs_service.commit.side_effect = None
    env.vcs_service.commit.return_value = None
    env.vcs_service.status.return_value = SimpleNamespace(head="d" * 40, dirty=False)
    env.artifacts.fingerprint_pdf.return_value = None
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    stamped = env.saved[-1]
    assert (stamped.source_commit, stamped.output_sha256) == ("d" * 40, None)


async def test__on_finished__unsaved_edits__pdf_is_not_tied_to_a_version(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.vcs_service.commit.side_effect = None
    env.vcs_service.commit.return_value = None
    env.vcs_service.status.return_value = SimpleNamespace(head="d" * 40, dirty=True)
    env.artifacts.fingerprint_pdf.return_value = PdfFingerprint(size=1, sha256="ef" * 32)
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    stamped = env.saved[-1]
    assert (stamped.source_commit, stamped.output_sha256) == (None, "ef" * 32)


async def test__on_finished__failure__record_is_not_stamped(tmp_path: Path) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.failed), "log")

    env.artifacts.fingerprint_pdf.assert_not_called()
    assert env.saved[-1].source_commit is None


async def test__on_finished__fingerprint_fails__build_result_is_kept(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.artifacts.fingerprint_pdf.side_effect = RuntimeError("disk")
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "log")

    assert env.saved[-1].status is CompileStatus.success
    assert env.doc_status is DocumentStatus.ok


# --- причина неудачной сборки ---


async def test__on_finished__latex_failure_without_runner_error__build_failed_with_explained_log(
    tmp_path: Path,
) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.failed), "! Undefined control sequence.")

    final = env.saved[-1]
    assert (final.error_code, final.error_detail) == ("build_failed", None)
    assert final.log.startswith("! Undefined control sequence.\n[error] build_failed: ")


async def test__on_finished__empty_runner_log_and_runner_error__log_is_the_explanation_not_empty(
    tmp_path: Path,
) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)
    error = JobError(JobErrorCategory.unavailable, "image_missing", "texlive/texlive:TL2024-historic")
    result = JobResult(
        status=JobStatus.failed, error=error, data=CompileResult(build_ok=False, finished_at=FINISHED_AT)
    )

    await env.hooks.on_finished(env.spec, result, "")

    final = env.saved[-1]
    assert (final.error_code, final.error_detail) == ("image_missing", "texlive/texlive:TL2024-historic")
    assert final.log.startswith("[error] image_missing: ")
    assert "texlive/texlive:TL2024-historic" in final.log.splitlines()[-1]


@pytest.mark.parametrize("code", ["timed_out", "runner_lost", "storage_unreachable", "disk_full", "job_lost"])
async def test__on_finished__runner_and_server_codes__recorded_with_log_block(tmp_path: Path, code: str) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)
    result = JobResult(status=JobStatus.failed, error=JobError(JobErrorCategory.unavailable, code))

    await env.hooks.on_finished(env.spec, result, "")

    final = env.saved[-1]
    assert final.error_code == code
    assert f"[error] {code}: " in final.log


async def test__on_finished__cancelled__recorded_as_cancelled_reason(tmp_path: Path) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, JobResult(status=JobStatus.cancelled), "[cancelled] by user")

    final = env.saved[-1]
    assert (final.status, final.error_code) == (CompileStatus.cancelled, "cancelled")


async def test__on_finished__quota_json_detail__dropped_from_record(tmp_path: Path) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)
    error = JobError(JobErrorCategory.unavailable, "quota_exceeded", '{"used": 3, "limit": 3}')

    await env.hooks.on_finished(env.spec, JobResult(status=JobStatus.failed, error=error), "[error] quota used up")

    final = env.saved[-1]
    assert (final.error_code, final.error_detail) == ("quota_exceeded", None)
    assert final.log.startswith("[error] quota used up\n[error] quota_exceeded: ")


async def test__on_finished__success__no_error_fields(tmp_path: Path) -> None:
    env = Env(tmp_path)
    await env.hooks.on_started(env.spec)

    await env.hooks.on_finished(env.spec, _result(JobStatus.succeeded), "ok")

    final = env.saved[-1]
    assert (final.error_code, final.error_detail, final.log) == (None, None, "ok")
