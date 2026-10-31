"""Выгрузка PDF на сервер Студии: когда делается, когда пропускается и как записывается итог."""

from __future__ import annotations

import hashlib
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.git_remote.client import (
    PdfUpload,
    PdfUploadReply,
    StudioServerError,
    StudioServerErrorCode,
)
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    StoreRemoteConfig,
    SyncState,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.use_cases.git_sync.publish_pdf import (
    PdfPublishStatus,
    PdfSkipReason,
    PublishPdfUC,
)

from tests.factories import make_project

SERVER_PROJECT = uuid4()
CRED = uuid4()
PDF = b"%PDF-1.7\nbody\n%%EOF\n"


class _Servers:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, PdfUpload]] = []
        self.error: Exception | None = None
        self.created = True

    async def upload_pdf(self, credential_id: UUID, upload: PdfUpload) -> PdfUploadReply:
        self.calls.append((credential_id, upload))
        if self.error is not None:
            raise self.error
        return PdfUploadReply(artifact_id="a1", created=self.created, size=upload.size)


class _Remotes:
    def __init__(self, url: str | None) -> None:
        self.url = url

    def read(self, _project: Any) -> StoreRemoteConfig | None:
        return None if self.url is None else StoreRemoteConfig(url=self.url, credential_id=CRED)


class _States:
    def __init__(self, state: SyncState | None = None) -> None:
        self.state = state

    def get(self, _folder: Path) -> SyncState | None:
        return self.state

    def save(self, _folder: Path, state: SyncState) -> None:
        self.state = state


class _Credentials:
    def __init__(self, origin: str | None) -> None:
        self.origin = origin

    async def get(self, credential_id: UUID) -> GitCredential | None:
        return GitCredential(
            id=credential_id,
            kind=GitCredentialKind.pat,
            label="studio",
            host="studio.example.org",
            username="hse",
            status=CredentialStatus.ok,
            created_at=datetime.now(UTC),
            origin=self.origin,
        )


class _Locks:
    @asynccontextmanager
    async def for_folder(self, _folder: Path):  # type: ignore[no-untyped-def]
        yield


class _Reader:
    def rev_parse(self, _folder: Path, _ref: str) -> str:
        return "a" * 40


class _Documents:
    def __init__(self, output: str | None) -> None:
        self.output = output

    async def execute(self, _inp: Any) -> Any:
        return SimpleNamespace(output_file=self.output)


class _Projects:
    def __init__(self, project: Any) -> None:
        self.project = project

    async def execute(self, _inp: Any) -> Any:
        return SimpleNamespace(project=self.project)


class Env:
    def __init__(self, tmp_path: Path, *, origin: str | None = "device", url: str | None = None, pdf: bool = True):
        self.folder = tmp_path / "proj"
        (self.folder / "coursework").mkdir(parents=True)
        if pdf:
            (self.folder / "coursework" / "main.pdf").write_bytes(PDF)
        self.project = make_project(self.folder)
        self.servers = _Servers()
        self.states = _States(SyncState(local_branch="master", remote_branch="master"))
        remote = url if url is not None else f"https://studio.example.org/git/{SERVER_PROJECT}.git"
        self.output: str | None = "coursework/main.pdf"
        self.uc = PublishPdfUC(
            project_repo_uc=_Projects(self.project),  # type: ignore[arg-type]
            document_uc=self,  # type: ignore[arg-type]
            store_remotes=_Remotes(remote),  # type: ignore[arg-type]
            state_repo=self.states,  # type: ignore[arg-type]
            credentials=_Credentials(origin),  # type: ignore[arg-type]
            servers=self.servers,  # type: ignore[arg-type]
            reader=_Reader(),  # type: ignore[arg-type]
            locks=_Locks(),  # type: ignore[arg-type]
            policy=GitSyncPolicy(),
        )

    async def execute(self, _inp: Any) -> Any:
        return SimpleNamespace(output_file=self.output)


async def test__publish__studio_project__uploads_with_fingerprint_and_records_success(tmp_path: Path) -> None:
    env = Env(tmp_path)

    result = await env.uc.execute(env.project.id, "coursework", pages=7)

    assert result.status is PdfPublishStatus.uploaded
    ((credential, upload),) = env.servers.calls
    assert credential == CRED
    assert (upload.project_id, upload.doc_id, upload.pages) == (SERVER_PROJECT, "coursework", 7)
    assert upload.sha256 == hashlib.sha256(PDF).hexdigest()
    assert upload.size == len(PDF)
    assert upload.source_commit == "a" * 40
    record = env.states.state.last_pdf_upload  # type: ignore[union-attr]
    assert (record.ok, record.doc_id, record.size) == (True, "coursework", len(PDF))  # type: ignore[union-attr]


async def test__publish__server_has_same_file__reported_unchanged(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.servers.created = False

    result = await env.uc.execute(env.project.id, "coursework")

    assert result.status is PdfPublishStatus.unchanged


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"origin": "manual"}, PdfSkipReason.not_studio_server),
        ({"url": "https://github.com/a/b.git"}, PdfSkipReason.not_studio_server),
    ],
)
async def test__publish__not_a_studio_server__skipped_without_network(
    tmp_path: Path, kwargs: dict[str, str], reason: PdfSkipReason
) -> None:
    env = Env(tmp_path, **kwargs)  # type: ignore[arg-type]

    result = await env.uc.execute(env.project.id, "coursework")

    assert (result.status, result.reason) == (PdfPublishStatus.skipped, reason)
    assert env.servers.calls == []


async def test__publish__disabled_in_project__skipped_unless_manual(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.states.state = replace(env.states.state, pdf_upload=False)  # type: ignore[type-var]

    auto = await env.uc.execute(env.project.id, "coursework")
    manual = await env.uc.execute(env.project.id, "coursework", manual=True)

    assert (auto.status, auto.reason) == (PdfPublishStatus.skipped, PdfSkipReason.disabled)
    assert manual.status is PdfPublishStatus.uploaded


async def test__publish__no_built_pdf__failed_with_hint_and_nothing_sent(tmp_path: Path) -> None:
    env = Env(tmp_path, pdf=False)

    result = await env.uc.execute(env.project.id, "coursework")

    assert (result.status, result.code) == (PdfPublishStatus.failed, "no_pdf_file")
    assert env.servers.calls == []
    assert env.states.state.last_pdf_upload.ok is False  # type: ignore[union-attr]


async def test__publish__fresh_copy_in_build_dir__preferred_over_stale_neighbour(tmp_path: Path) -> None:
    env = Env(tmp_path)
    fresh = env.folder / "coursework" / ".build" / "coursework"
    fresh.mkdir(parents=True)
    (fresh / "main.pdf").write_bytes(PDF + b"fresh")

    await env.uc.execute(env.project.id, "coursework")

    assert env.servers.calls[0][1].size == len(PDF) + 5


async def test__publish__output_outside_folder_or_not_pdf__refused(tmp_path: Path) -> None:
    env = Env(tmp_path)
    (tmp_path / "secret.pdf").write_bytes(PDF)

    env.output = "../secret.pdf"
    outside = await env.uc.execute(env.project.id, "coursework")
    env.output = "coursework/slides.pptx"
    other = await env.uc.execute(env.project.id, "coursework")

    assert (outside.code, other.code) == ("no_pdf_file", "not_pdf")
    assert env.servers.calls == []


async def test__publish__oversized_pdf__failed_before_upload(tmp_path: Path) -> None:
    env = Env(tmp_path)
    env.uc._policy = GitSyncPolicy(max_pdf_upload_bytes=4)  # noqa: SLF001

    result = await env.uc.execute(env.project.id, "coursework")

    assert (result.status, result.code) == (PdfPublishStatus.failed, StudioServerErrorCode.pdf_too_large)
    assert env.servers.calls == []


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (StudioServerError(StudioServerErrorCode.pdf_forbidden), "pdf_forbidden"),
        (StudioServerError(StudioServerErrorCode.unreachable), "git_server_unreachable"),
        (GitSyncError(GitErrorCode.auth_failed, "войдите заново"), "auth_failed"),
        (RuntimeError("boom"), "git_server_unreachable"),
    ],
)
async def test__publish__server_refuses__failure_recorded_for_the_window(
    tmp_path: Path, error: Exception, code: str
) -> None:
    env = Env(tmp_path)
    env.servers.error = error

    result = await env.uc.execute(env.project.id, "coursework")

    assert (result.status, result.code) == (PdfPublishStatus.failed, code)
    record = env.states.state.last_pdf_upload  # type: ignore[union-attr]
    assert (record.ok, record.code) == (False, code)  # type: ignore[union-attr]
    assert record.detail  # type: ignore[union-attr]
