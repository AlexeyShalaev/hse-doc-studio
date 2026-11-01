"""Сдача на сервере: архив уходит в хранилище, папка пакета не создаётся, скачивание попадает в аудит."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.enums import JobStatus
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.pack import PackResult
from hse_doc_studio.use_cases.submission.get_submission_file import GetSubmissionFileInput, GetSubmissionFileUC
from hse_doc_studio.use_cases.submission.list_submissions import ListSubmissionsInput, ListSubmissionsUC

from tests.contract.test_submission_contract import make_submission
from tests.factories import make_project, make_template_version
from tests.fakes.submission import FakeSubmissionArchive, InMemoryPackSubmissionRepository, RecordingSubmissionAudit
from tests.unit.use_cases.submission.test_create_submission import Harness, _doc

pytestmark = pytest.mark.unit


def _server_harness(tmp_path: Path) -> tuple[Harness, FakeSubmissionArchive]:
    h = Harness(tmp_path, [_doc("tz", ".pdf")], {"tz/_custom/tz.pdf"})
    archive = FakeSubmissionArchive()
    h.uc._archive = archive  # noqa: SLF001
    return h, archive


async def test__create_submission__server__archive_goes_to_storage_without_package_folder(tmp_path: Path) -> None:
    h, archive = _server_harness(tmp_path)
    (tmp_path / "submissions").mkdir()
    packed_archive = ArtifactRef("submissions/final-pack.zip", "0" * 64, 10)
    (tmp_path / packed_archive.path).write_bytes(b"PK-archive")
    h.dispatcher.pack_result = JobResult(status=JobStatus.succeeded, data=PackResult(archive=packed_archive))

    out = await h.create(None)

    assert h.dispatcher.specs[-1].payload.keep_folder is False
    record = out.submission
    assert record.output_dir is None
    assert record.artifact_key is not None
    assert archive.objects[record.artifact_key] == b"PK-archive"
    assert record.artifact_key.startswith(f"artifacts/{h.project.id}/submissions/{record.id}/")
    assert not (tmp_path / packed_archive.path).exists()
    assert h.submission_repo.save.call_args.args[0] is record


async def test__create_submission__local__keeps_folder_and_has_no_artifact_key(tmp_path: Path) -> None:
    h = Harness(tmp_path, [_doc("tz", ".pdf")], {"tz/_custom/tz.pdf"})

    out = await h.create(None)

    assert h.dispatcher.specs[-1].payload.keep_folder is True
    assert out.submission.output_dir is not None
    assert out.submission.artifact_key is None


class _Env:
    def __init__(self, tmp_path: Path, *, links: bool = True) -> None:
        self.project = make_project(folder=tmp_path)
        project_repo = MagicMock()
        project_repo.get.return_value = self.project
        index = MagicMock()
        index.list_known.return_value = [tmp_path]
        self.repo = InMemoryPackSubmissionRepository()
        self.archive = FakeSubmissionArchive(links=links)
        self.audit = RecordingSubmissionAudit()
        self.get_file = GetSubmissionFileUC(project_repo, index, self.repo, self.archive, self.audit)
        templates = MagicMock()
        templates.get_version.return_value = make_template_version()
        self.list = ListSubmissionsUC(project_repo, index, self.repo, templates, self.archive)
        self.tmp_path = tmp_path

    async def stored(self, content: bytes = b"PK-archive"):  # noqa: ANN202
        record = make_submission(self.tmp_path, output_dir=None)
        key = f"artifacts/{self.project.id}/submissions/{record.id}/{record.output_path.name}"
        self.archive.objects[key] = content
        record.artifact_key = key
        await self.repo.save(record)
        return record


async def test__get_submission_file__server_link__redirects_and_audits_download(tmp_path: Path) -> None:
    env = _Env(tmp_path)
    record = await env.stored()
    set_current_actor(Actor.user("anna"))

    out = await env.get_file.execute(GetSubmissionFileInput(env.project.id, record.id))

    assert out.redirect_url is not None
    assert out.redirect_url.startswith("https://s3.test/")
    assert out.download_name == record.output_path.name
    assert env.audit.events == [("anna", env.project.id, record.id, "link")]


async def test__get_submission_file__server_without_links__streams_and_audits(tmp_path: Path) -> None:
    env = _Env(tmp_path, links=False)
    record = await env.stored(b"PK-stream")
    set_current_actor(Actor.user("anna"))

    out = await env.get_file.execute(GetSubmissionFileInput(env.project.id, record.id))

    assert out.stream is not None
    assert b"".join([chunk async for chunk in out.stream]) == b"PK-stream"
    assert env.audit.events == [("anna", env.project.id, record.id, "stream")]


async def test__get_submission_file__object_missing__not_found_and_no_audit(tmp_path: Path) -> None:
    env = _Env(tmp_path)
    record = await env.stored()
    env.archive.objects.clear()

    with pytest.raises(NotFoundError):
        await env.get_file.execute(GetSubmissionFileInput(env.project.id, record.id))

    assert env.audit.events == []


async def test__get_submission_file__unknown_submission__not_found_and_no_audit(tmp_path: Path) -> None:
    env = _Env(tmp_path)

    with pytest.raises(NotFoundError):
        await env.get_file.execute(GetSubmissionFileInput(env.project.id, uuid4()))

    assert env.audit.events == []


async def test__list_submissions__server_record__size_comes_from_storage(tmp_path: Path) -> None:
    env = _Env(tmp_path)
    record = await env.stored(b"12345")

    out = await env.list.execute(ListSubmissionsInput(env.project.id))

    assert [(i.record.id, i.size_bytes) for i in out.items] == [(record.id, 5)]
