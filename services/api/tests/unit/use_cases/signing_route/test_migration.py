"""Перенос маршрутов 0.20.0 (docs/design/signing-route.md, 12.11): какие документы переносятся, откуда берётся
версия на подписи (текущая сборка, архив сборок), что потеряно и что перенос пишет."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus, EngineType
from hse_doc_studio.core.signing_route.entities import DocSnapshot, RouteStatus, SigningRoute
from hse_doc_studio.core.value_objects import PinnedPdf
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.use_cases.signing_route.migration import (
    BuildArchive,
    MigrationOutcome,
    RestoredFrom,
    RouteMigration,
    unmigrated_docs,
)
from hse_doc_studio.use_cases.signing_route.pinning import RoutePinning

SENT_AT = datetime(2026, 11, 10, 10, 23, tzinfo=UTC)
NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
DOC, DOC2 = "topic_application", "project_proposal"


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class _Templates:
    def resolve_signing_output(self, project: Any, doc: Any, version: Any) -> str | None:
        return f"out/{doc.id}.pdf"


def _point(folder: Path) -> Any:
    documents = {doc_id: SimpleNamespace(id=doc_id) for doc_id in (DOC, DOC2)}
    return SimpleNamespace(
        project=SimpleNamespace(folder=folder), project_id=uuid4(), documents=documents, version=None
    )


def _build(folder: Path, doc_id: str, content: bytes) -> None:
    path = folder / "out" / f"{doc_id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _route(sent: dict[str, bytes], *, status: RouteStatus = RouteStatus.active, **snapshot: Any) -> SigningRoute:
    return SigningRoute(
        id=uuid4(),
        project_id=uuid4(),
        profile_id="topic-approval",
        created_by=uuid4(),
        status=status,
        round=1,
        sent_at=SENT_AT,
        docs=tuple(sent),
        snapshot={doc_id: DocSnapshot(_sha(content), "marks", **snapshot) for doc_id, content in sent.items()},
    )


@dataclass
class _Archive:
    """Архив сборок: PDF по документу; запоминает, что спрашивали."""

    pdfs: dict[str, list[bytes]] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    async def find(self, project_id: UUID, folder: Path, doc_id: str, sha256: str) -> bytes | None:
        self.asked.append(doc_id)
        return next((pdf for pdf in self.pdfs.get(doc_id, []) if _sha(pdf) == sha256), None)


def _migration(repo: JsonSignatureRepository, archive: _Archive | None = None) -> RouteMigration:
    return RouteMigration(RoutePinning(repo, cast(Any, _Templates())), archive)


async def test__unchanged_build__pinned_from_it_with_the_route_send_time(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    _build(tmp_path, DOC, b"%PDF sent")
    route = _route({DOC: b"%PDF sent"})
    archive = _Archive()

    migration = await _migration(repo, archive).migrate(_point(tmp_path), route, at=NOW)

    assert migration is not None
    assert (migration.outcome, dict(migration.restored), migration.lost) == (
        MigrationOutcome.pinned,
        {DOC: RestoredFrom.build},
        (),
    )
    assert archive.asked == []
    pinned = repo.get_state(tmp_path).pinned[DOC]
    assert (pinned.sha256, pinned.pinned_at, pinned.route_id, pinned.round) == (
        _sha(b"%PDF sent"),
        SENT_AT.isoformat(),
        str(route.id),
        1,
    )
    assert (tmp_path / pinned.path).read_bytes() == b"%PDF sent"
    # Временные файлы архива и копии убраны.
    assert sorted(p.name for p in (tmp_path / ".hse-studio" / "frozen").iterdir()) == [f"{DOC}.source.pdf"]


async def test__rebuilt_with_changes__pinned_from_the_archive__lost_when_archive_forgot_it(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    _build(tmp_path, DOC, b"%PDF edited")
    _build(tmp_path, DOC2, b"%PDF edited too")
    route = _route({DOC: b"%PDF sent", DOC2: b"%PDF sent too"})
    archive = _Archive({DOC: [b"%PDF edited", b"%PDF sent", b"%PDF older"], DOC2: [b"%PDF edited too"]})

    migration = await _migration(repo, archive).migrate(_point(tmp_path), route, at=NOW)

    assert migration is not None
    assert migration.outcome is MigrationOutcome.needs_new_version
    assert (dict(migration.restored), migration.lost) == ({DOC: RestoredFrom.archive}, (DOC2,))
    assert migration.audit_details() == {
        "outcome": "needs_new_version",
        "docs": [DOC, DOC2],
        "restored": [{"doc_id": DOC, "sha256": _sha(b"%PDF sent"), "from": "archive"}],
        "lost": [DOC2],
    }
    state = repo.get_state(tmp_path)
    assert set(state.pinned) == {DOC}
    assert (tmp_path / state.pinned[DOC].path).read_bytes() == b"%PDF sent"
    # Рабочая сборка не тронута.
    assert (tmp_path / "out" / f"{DOC}.pdf").read_bytes() == b"%PDF edited"
    assert sorted(p.name for p in (tmp_path / ".hse-studio" / "frozen").iterdir()) == [f"{DOC}.source.pdf"]


async def test__second_pass__nothing_to_migrate(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    _build(tmp_path, DOC, b"%PDF sent")
    route = _route({DOC: b"%PDF sent"})
    migration = _migration(repo)

    assert await migration.migrate(_point(tmp_path), route, at=NOW) is not None
    before = repo.get_state(tmp_path)
    assert await migration.migrate(_point(tmp_path), route, at=NOW) is None
    assert repo.get_state(tmp_path) == before


async def test__held_route_without_any_version__nothing_written(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    _build(tmp_path, DOC, b"%PDF edited")
    route = _route({DOC: b"%PDF sent"}, status=RouteStatus.paused)

    assert await _migration(repo, _Archive()).migrate(_point(tmp_path), route, at=NOW) is None
    assert repo.get_state(tmp_path).pinned == {}


async def test__active_route_without_any_version__lost_is_reported_for_the_stop(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    route = _route({DOC: b"%PDF sent"})

    migration = await _migration(repo, _Archive()).migrate(_point(tmp_path), route, at=NOW)

    assert migration is not None
    assert (migration.outcome, migration.lost) == (MigrationOutcome.needs_new_version, (DOC,))


def test__unmigrated_docs__only_0_20_0_documents_without_a_version_of_a_holding_route() -> None:
    sent = {DOC: b"%PDF a", DOC2: b"%PDF b"}
    empty = JsonSignatureRepository().get_state(Path("/nonexistent"))
    pinned = replace(
        empty,
        pinned={DOC: PinnedPdf(path="x", sha256="s", size=1, pinned_at="", route_id="r", round=1)},
    )

    assert unmigrated_docs(_route(sent), empty) == (DOC, DOC2)
    assert unmigrated_docs(_route(sent), pinned) == (DOC2,)
    # Отправлен 0.21 и новее (`sent_at` в снимке): удалённую версию перенос не возвращает, это `sent_changed`.
    assert unmigrated_docs(_route(sent, sent_at=SENT_AT), empty) == ()
    for status in (RouteStatus.draft, RouteStatus.cancelled, RouteStatus.archived):
        assert unmigrated_docs(_route(sent, status=status), empty) == ()
    for status in (RouteStatus.paused, RouteStatus.returned, RouteStatus.completed):
        assert unmigrated_docs(_route(sent, status=status), empty) == (DOC, DOC2)


@dataclass
class _Compiles:
    records: list[CompileRecord]

    async def list_for_document(self, project_folder: Path, doc_id: str) -> list[CompileRecord]:
        return [r for r in self.records if r.doc_id == doc_id]


@dataclass
class _Artifacts:
    pdfs: dict[UUID, bytes]
    read: list[UUID] = field(default_factory=list)

    async def read_archived_pdf(self, project_id: UUID, workspace: Path, doc_id: str, job_id: UUID) -> bytes:
        self.read.append(job_id)
        if job_id not in self.pdfs:
            raise FileNotFoundError(str(job_id))
        return self.pdfs[job_id]


def _record(n: int, content: bytes | None, *, status: CompileStatus = CompileStatus.success, sha: bool = True) -> Any:
    at = SENT_AT + timedelta(minutes=n)
    return CompileRecord(
        id=uuid4(),
        project_folder=Path("/p"),
        doc_id=DOC,
        engine=EngineType.xelatex,
        status=status,
        started_at=at,
        finished_at=at,
        log="",
        output_path=None,
        check_results=[],
        pages=1,
        output_sha256=_sha(content) if content is not None and sha else None,
    )


async def test__build_archive__newest_matching_first__bytes_verified__depth_limited() -> None:
    sent = b"%PDF sent"
    old = _record(0, sent)  # за пределами глубины архива
    failed = _record(1, None, status=CompileStatus.failure)
    unknown = _record(2, sent, sha=False)  # старая запись без отпечатка
    lying = _record(3, sent)  # отпечаток совпал, а файл в архиве другой
    gone = _record(4, sent)  # архив уже вытеснил файл
    match = _record(5, sent)
    newer = [_record(6 + n, b"%%PDF edit %d" % n) for n in range(3)]
    records = [old, failed, unknown, lying, gone, match, *newer]
    pdfs = {old.id: sent, unknown.id: sent, lying.id: b"%PDF other", match.id: sent}
    pdfs |= {r.id: b"%%PDF edit %d" % n for n, r in enumerate(newer)}
    artifacts = _Artifacts(pdfs)
    archive = BuildArchive(cast(Any, _Compiles(records)), cast(Any, artifacts), depth=7)

    assert await archive.find(uuid4(), Path("/p"), DOC, _sha(sent)) == sent
    # Сначала сборки с тем же отпечатком, новые первыми; до старой за глубиной архива дело не доходит.
    assert artifacts.read == [match.id]

    artifacts.read.clear()
    pdfs.pop(match.id)
    assert await archive.find(uuid4(), Path("/p"), DOC, _sha(sent)) == sent
    assert artifacts.read == [match.id, gone.id, lying.id, unknown.id]

    artifacts.read.clear()
    pdfs.pop(unknown.id)
    assert await archive.find(uuid4(), Path("/p"), DOC, _sha(sent)) is None
    assert old.id not in artifacts.read
