"""Сборки в локальной Студии и в облаке: статус и получение готового PDF (docs/design/connected-devices.md, часть 3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.devices.builds import BuildRelation, FetchStatus
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, EngineType
from hse_doc_studio.core.git_remote.client import (
    CloudPdfReply,
    StudioServerError,
    StudioServerErrorCode,
)
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind, StoreRemoteConfig
from hse_doc_studio.use_cases.devices.local_builds import FETCHED_MARK, LocalBuildsUC

from tests.factories import make_document, make_project

SERVER_PROJECT = uuid4()
CRED = uuid4()
CLOUD_COMPILE = uuid4()
T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
PDF = b"%PDF-1.7\ncloud\n%%EOF\n"
SHA_CLOUD = "c" * 64
SHA_LOCAL = "1" * 64
HEAD = "a" * 40


class Servers:
    def __init__(self, raw: dict[str, Any] | Exception) -> None:
        self.raw = raw
        self.downloads: list[tuple[str, str | None]] = []
        self.error: Exception | None = None
        self.unchanged = False

    async def project_builds(self, _credential_id: UUID, _project_id: UUID) -> dict[str, Any]:
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw

    async def download_cloud_pdf(
        self,
        _credential_id: UUID,
        _project_id: UUID,
        doc_id: str,
        dest: Path,
        *,
        known_sha256: str | None,
        max_bytes: int,
    ) -> CloudPdfReply:
        self.downloads.append((doc_id, known_sha256))
        if self.error is not None:
            raise self.error
        if self.unchanged:
            return CloudPdfReply(unchanged=True, sha256=known_sha256)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(PDF)
        return CloudPdfReply(False, SHA_CLOUD, len(PDF), HEAD, T0, 2)


class Compiles:
    def __init__(self, *records: CompileRecord) -> None:
        self.records = list(records)

    async def list_for_document(self, _folder: Path, doc_id: str) -> list[CompileRecord]:
        return [r for r in self.records if r.doc_id == doc_id]

    async def save(self, record: CompileRecord) -> None:
        self.records = [r for r in self.records if r.id != record.id] + [record]


def raw_builds(
    *, cloud_at: datetime = T0, commit: str | None = HEAD, size: int = len(PDF), fresh: bool | None = True
) -> dict[str, Any]:
    return {
        "head": HEAD,
        "dirty": False,
        "max_pdf_bytes": 100 * 1024 * 1024,
        "documents": [
            {
                "doc_id": "vkr",
                "cloud": {
                    "at": cloud_at.isoformat(),
                    "commit": commit,
                    "pages": 2,
                    "fresh": fresh,
                    "sha256": SHA_CLOUD,
                    "size": size,
                    "compile_id": str(CLOUD_COMPILE),
                },
                "cloud_running": False,
                "studio": None,
            }
        ],
    }


def local_record(
    folder: Path, *, at: datetime, sha: str | None = SHA_LOCAL, commit: str | None = HEAD
) -> CompileRecord:
    return CompileRecord(
        id=uuid4(),
        project_folder=folder,
        doc_id="vkr",
        engine=EngineType.xelatex,
        status=CompileStatus.success,
        started_at=at,
        finished_at=at,
        log="log",
        output_path=None,
        check_results=[],
        pages=1,
        source_commit=commit,
        output_sha256=sha,
    )


def build(
    tmp_path: Path,
    servers: Servers,
    *records: CompileRecord,
    dirty: bool = False,
    connected: bool = True,
) -> tuple[LocalBuildsUC, Compiles]:
    project = make_project(folder=tmp_path, documents=[make_document("vkr")])
    compiles = Compiles(*records)
    url = f"https://studio.example.org/git/{SERVER_PROJECT}.git" if connected else "https://github.com/a/b.git"
    credential = GitCredential(
        CRED, GitCredentialKind.pat, "l", "studio.example.org", "hse", CredentialStatus.ok, T0, origin="device"
    )

    class Projects:
        async def execute(self, _inp: Any) -> Any:
            return SimpleNamespace(project=project)

    class Documents:
        async def execute(self, _inp: Any) -> Any:
            return SimpleNamespace(output_file="vkr/vkr.pdf")

    class Credentials:
        async def get(self, _id: UUID) -> GitCredential:
            return credential

    class Remotes:
        def read(self, _project: Any) -> StoreRemoteConfig:
            return StoreRemoteConfig(url=url, credential_id=CRED)

    class States:
        def get(self, _folder: Path) -> None:
            return None

    class Vcs:
        def status(self, _project: Any, _settings: Any) -> Any:
            return SimpleNamespace(available=True, initialized=True, head=HEAD, dirty=dirty)

    uc = LocalBuildsUC(
        project_uc=Projects(),  # type: ignore[arg-type]
        document_uc=Documents(),  # type: ignore[arg-type]
        project_repo=SimpleNamespace(),  # type: ignore[arg-type]
        compile_repo=compiles,  # type: ignore[arg-type]
        vcs=Vcs(),  # type: ignore[arg-type]
        servers=servers,  # type: ignore[arg-type]
        credentials=Credentials(),  # type: ignore[arg-type]
        store_remotes=Remotes(),  # type: ignore[arg-type]
        state_repo=States(),  # type: ignore[arg-type]
    )
    return uc, compiles


# --- статус ---


async def test__status__cloud_built_and_this_studio_has_nothing__says_so_per_document(tmp_path: Path) -> None:
    uc, _ = build(tmp_path, Servers(raw_builds()))

    found = await uc.status(uuid4())

    (doc,) = found.documents
    assert (doc.relation, doc.can_fetch, doc.local) == (BuildRelation.cloud_only, True, None)
    assert doc.cloud is not None
    assert (doc.cloud.commit, doc.cloud.fresh) == (HEAD, True)
    assert (found.connected, found.cloud_error, found.cloud_head) == (True, None, HEAD)


async def test__status__same_pdf_on_both_sides__relation_same_nothing_to_fetch(tmp_path: Path) -> None:
    uc, _ = build(tmp_path, Servers(raw_builds()), local_record(tmp_path, at=T0, sha=SHA_CLOUD))

    (doc,) = (await uc.status(uuid4())).documents

    assert (doc.relation, doc.can_fetch) == (BuildRelation.same, False)


async def test__status__older_local_build__cloud_newer_and_fetchable(tmp_path: Path) -> None:
    uc, _ = build(tmp_path, Servers(raw_builds()), local_record(tmp_path, at=T0 - timedelta(hours=1)))

    (doc,) = (await uc.status(uuid4())).documents

    assert (doc.relation, doc.can_fetch) == (BuildRelation.cloud_newer, True)
    assert doc.local is not None
    assert doc.local.fresh is True


async def test__status__local_build_of_older_version_or_dirty_tree__is_not_fresh(tmp_path: Path) -> None:
    old = local_record(tmp_path, at=T0, commit="b" * 40)
    uc, _ = build(tmp_path, Servers(raw_builds()), old)
    dirty_uc, _ = build(tmp_path, Servers(raw_builds()), local_record(tmp_path, at=T0), dirty=True)

    (stale,) = (await uc.status(uuid4())).documents
    (unsaved,) = (await dirty_uc.status(uuid4())).documents

    assert stale.local is not None
    assert unsaved.local is not None
    assert (stale.local.fresh, unsaved.local.fresh) == (False, False)


async def test__status__no_connection_to_the_server__local_side_is_still_shown_with_the_reason(tmp_path: Path) -> None:
    servers = Servers(StudioServerError(StudioServerErrorCode.unreachable))
    uc, _ = build(tmp_path, servers, local_record(tmp_path, at=T0))

    found = await uc.status(uuid4())

    assert found.cloud_error == StudioServerErrorCode.unreachable
    assert found.documents[0].local is not None
    assert found.documents[0].cloud is None


async def test__status__project_not_from_a_studio_server__not_connected(tmp_path: Path) -> None:
    uc, _ = build(tmp_path, Servers(raw_builds()), connected=False)

    found = await uc.status(uuid4())

    assert found.connected is False
    assert found.documents[0].cloud is None


# --- получение ---


async def test__fetch__no_local_build__downloads_installs_pdf_and_records_it_under_the_cloud_compile_id(
    tmp_path: Path,
) -> None:
    servers = Servers(raw_builds())
    uc, compiles = build(tmp_path, servers)

    (outcome,) = await uc.fetch(uuid4(), "vkr")

    assert (outcome.status, outcome.size) == (FetchStatus.downloaded, len(PDF))
    assert (tmp_path / "vkr" / "vkr.pdf").read_bytes() == PDF
    (record,) = compiles.records
    assert record.id == CLOUD_COMPILE
    assert record.status is CompileStatus.success
    assert record.log.startswith(FETCHED_MARK)
    assert (record.source_commit, record.output_sha256, record.pages) == (HEAD, SHA_CLOUD, 2)
    assert list((tmp_path / "vkr" / ".build" / "vkr").glob("*.part")) == []


async def test__fetch__same_fingerprint__nothing_is_downloaded(tmp_path: Path) -> None:
    servers = Servers(raw_builds())
    uc, _ = build(tmp_path, servers, local_record(tmp_path, at=T0, sha=SHA_CLOUD))

    (outcome,) = await uc.fetch(uuid4(), "vkr")

    assert outcome.status is FetchStatus.unchanged
    assert servers.downloads == []


async def test__fetch__newer_local_build__is_kept_unless_forced(tmp_path: Path) -> None:
    servers = Servers(raw_builds(cloud_at=T0 - timedelta(hours=1)))
    uc, compiles = build(tmp_path, servers, local_record(tmp_path, at=T0))
    existing = tmp_path / "vkr" / "vkr.pdf"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"%PDF-local")

    (kept,) = await uc.fetch(uuid4(), "vkr")
    (forced,) = await uc.fetch(uuid4(), "vkr", force=True)

    assert kept.status is FetchStatus.kept_local
    assert forced.status is FetchStatus.downloaded
    assert existing.read_bytes() == PDF
    assert len(compiles.records) == 2


async def test__fetch__file_larger_than_the_limit__is_not_downloaded(tmp_path: Path) -> None:
    servers = Servers(raw_builds(size=200 * 1024 * 1024))
    uc, _ = build(tmp_path, servers)

    (outcome,) = await uc.fetch(uuid4(), "vkr")

    assert outcome.status is FetchStatus.too_large
    assert servers.downloads == []


async def test__fetch__auto_mode__takes_only_the_build_of_the_version_the_person_has(tmp_path: Path) -> None:
    servers = Servers(raw_builds(commit="b" * 40))
    uc, _ = build(tmp_path, servers)

    (auto,) = await uc.fetch(uuid4(), "vkr", auto=True)
    (manual,) = await uc.fetch(uuid4(), "vkr")

    assert auto.status is FetchStatus.skipped_stale
    assert manual.status is FetchStatus.downloaded
    assert len(servers.downloads) == 1


async def test__fetch__auto_mode_with_unsaved_edits__is_skipped(tmp_path: Path) -> None:
    uc, _ = build(tmp_path, Servers(raw_builds()), dirty=True)

    (outcome,) = await uc.fetch(uuid4(), "vkr", auto=True)

    assert outcome.status is FetchStatus.skipped_stale


async def test__fetch__without_document__takes_every_document_that_has_a_cloud_build(tmp_path: Path) -> None:
    raw = raw_builds()
    raw["documents"].append({"doc_id": "other", "cloud": None, "cloud_running": False, "studio": None})
    uc, _ = build(tmp_path, Servers(raw))

    outcomes = await uc.fetch(uuid4(), None)

    assert [(o.doc_id, o.status) for o in outcomes] == [("vkr", FetchStatus.downloaded)]


async def test__fetch__document_without_cloud_build__reports_it(tmp_path: Path) -> None:
    raw = raw_builds()
    raw["documents"][0]["cloud"] = None
    uc, _ = build(tmp_path, Servers(raw))

    (outcome,) = await uc.fetch(uuid4(), "vkr")

    assert outcome.status is FetchStatus.no_cloud_build


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (StudioServerErrorCode.cloud_pdf_too_large, FetchStatus.too_large),
        (StudioServerErrorCode.cloud_pdf_missing, FetchStatus.no_cloud_build),
        (StudioServerErrorCode.unreachable, FetchStatus.failed),
    ],
)
async def test__fetch__server_refusals__map_to_outcomes_and_leave_no_partial_file(
    tmp_path: Path, code: str, status: FetchStatus
) -> None:
    servers = Servers(raw_builds())
    servers.error = StudioServerError(code)
    uc, compiles = build(tmp_path, servers)

    (outcome,) = await uc.fetch(uuid4(), "vkr")

    assert outcome.status is status
    assert compiles.records == []
    assert not (tmp_path / "vkr" / "vkr.pdf").exists()


async def test__fetch__server_says_unchanged__keeps_local_file(tmp_path: Path) -> None:
    servers = Servers(raw_builds())
    servers.unchanged = True
    uc, compiles = build(tmp_path, servers, local_record(tmp_path, at=T0 - timedelta(hours=1)))

    (outcome,) = await uc.fetch(uuid4(), "vkr")

    assert outcome.status is FetchStatus.unchanged
    assert len(compiles.records) == 1
