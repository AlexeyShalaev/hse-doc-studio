"""Снятие версии на подписи маршрутом (docs/design/signing-route.md, 12.3 и 12.4): копия, хэш копии, сверка,
переименование и запись `pinned`; отмена снимает только версии своего маршрута."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors, decode_anchors, encode_anchors
from hse_doc_studio.core.signing_route.entities import SigningRoute
from hse_doc_studio.core.signing_route.readiness import DocChangedError
from hse_doc_studio.core.value_objects import PinnedPdf
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.use_cases.signing_route.pinning import PinnedVersion, RoutePinning

AT = datetime(2026, 11, 10, 14, 32, tzinfo=UTC)
DOC, DOC2 = "application", "proposal"


class _Templates:
    def resolve_signing_output(self, project: Any, doc: Any, version: Any) -> str | None:
        return doc.output

    def resolve_instance_source(self, project: Any, doc: Any, version: Any) -> tuple[str, str]:
        return f"out/{doc.id}.tex", f"out/{doc.id}.pdf"


def _point(folder: Path, *, unbuilt: tuple[str, ...] = ()) -> Any:
    documents = {
        doc_id: SimpleNamespace(id=doc_id, output=None if doc_id in unbuilt else f"out/{doc_id}.pdf")
        for doc_id in (DOC, DOC2)
    }
    return SimpleNamespace(project=SimpleNamespace(folder=folder), documents=documents, version=None)


def _route(round_: int = 1) -> SigningRoute:
    return SigningRoute(id=uuid4(), project_id=uuid4(), profile_id="topic", created_by=uuid4(), round=round_)


def _build(folder: Path, doc_id: str, content: bytes) -> str:
    path = folder / "out" / f"{doc_id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _pinning(repo: JsonSignatureRepository) -> RoutePinning:
    return RoutePinning(repo, cast(Any, _Templates()))


def _leftovers(folder: Path) -> list[str]:
    frozen = folder / ".hse-studio" / "frozen"
    return sorted(p.name for p in frozen.iterdir() if p.name.endswith(".tmp")) if frozen.is_dir() else []


async def test__pin__copies_the_build_and_records_the_version(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    sha = _build(tmp_path, DOC, b"%PDF v1")
    route = _route()

    versions = await _pinning(repo).pin(_point(tmp_path), route, {DOC: sha}, at=AT)

    assert versions == (PinnedVersion(DOC, sha, 7),)
    pinned = repo.get_state(tmp_path).pinned[DOC]
    assert pinned == PinnedPdf(
        path=".hse-studio/frozen/application.source.pdf",
        sha256=sha,
        size=7,
        pinned_at=AT.isoformat(),
        route_id=str(route.id),
        round=1,
    )
    assert (tmp_path / pinned.path).read_bytes() == b"%PDF v1"
    assert _leftovers(tmp_path) == []


async def test__pin__build_changed_after_preview__doc_changed_and_nothing_written(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    sha = _build(tmp_path, DOC, b"%PDF v1")
    old = _build(tmp_path, DOC2, b"%PDF v1 proposal")
    _build(tmp_path, DOC2, b"%PDF v2 proposal")

    with pytest.raises(DocChangedError) as caught:
        await _pinning(repo).pin(_point(tmp_path), _route(), {DOC: sha, DOC2: old}, at=AT)

    assert caught.value.doc_ids == (DOC2,)
    assert repo.get_state(tmp_path).pinned == {}
    assert not (tmp_path / ".hse-studio/frozen/application.source.pdf").exists()
    assert _leftovers(tmp_path) == []


async def test__pin__unbuilt_document__keeps_its_version_under_the_new_round(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    sha = _build(tmp_path, DOC, b"%PDF v1")
    first = _route()
    await _pinning(repo).pin(_point(tmp_path), first, {DOC: sha}, at=AT)

    later = replace(first, round=2)
    await _pinning(repo).pin(_point(tmp_path, unbuilt=(DOC,)), later, {DOC: sha}, at=AT)

    assert (repo.get_state(tmp_path).pinned[DOC].round, repo.get_state(tmp_path).pinned[DOC].sha256) == (2, sha)


async def test__pin__nothing_to_build_from__doc_changed(tmp_path: Path) -> None:
    with pytest.raises(DocChangedError):
        await _pinning(JsonSignatureRepository()).pin(_point(tmp_path), _route(), {DOC: "0" * 64}, at=AT)


async def test__unpin__only_this_routes_versions_and_files(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    route, other = _route(), _route()
    await _pinning(repo).pin(_point(tmp_path), route, {DOC: _build(tmp_path, DOC, b"%PDF a")}, at=AT)
    await _pinning(repo).pin(_point(tmp_path), other, {DOC2: _build(tmp_path, DOC2, b"%PDF b")}, at=AT)
    route = replace(route, docs=(DOC,))

    unpinned = _pinning(repo).unpin(_point(tmp_path), route)

    assert unpinned == (DOC,)
    assert set(repo.get_state(tmp_path).pinned) == {DOC2}
    assert not (tmp_path / ".hse-studio/frozen/application.source.pdf").exists()
    assert (tmp_path / ".hse-studio/frozen/proposal.source.pdf").exists()
    assert _pinning(repo).unpin(_point(tmp_path), route) == ()


# --- копия якорей сборки (signing-route.md, 15.17.6) ---

ANCHORS = ".hse-studio/frozen/application.source.anchors.json"


def _build_anchors(folder: Path, doc_id: str, sha: str, anchor_id: str = "supervisor") -> None:
    anchors = BuildAnchors(sha, (BuildAnchor(anchor_id, AnchorKind.sign, 1, 169.5, 186.9, 25.5),))
    path = folder / "out" / ".build" / doc_id / f"{doc_id}.anchors.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_anchors(anchors))


def _pinned_anchors(folder: Path) -> BuildAnchors | None:
    path = folder / ANCHORS
    return decode_anchors(path.read_bytes()) if path.exists() else None


async def test__pin__anchors_of_the_same_build__copied_next_to_the_version(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    sha = _build(tmp_path, DOC, b"%PDF v1")
    _build_anchors(tmp_path, DOC, sha)

    await _pinning(repo).pin(_point(tmp_path), _route(), {DOC: sha}, at=AT)

    copied = _pinned_anchors(tmp_path)
    assert copied is not None
    assert copied.pdf_sha256 == sha
    assert [a.id for a in copied.anchors] == ["supervisor"]
    assert _leftovers(tmp_path) == []


async def test__pin__anchors_of_another_pdf__not_copied_and_old_copy_removed(tmp_path: Path) -> None:
    # Сборка раннером прежней версии: PDF новый, якоря в `.build` от прошлой сборки.
    repo = JsonSignatureRepository()
    first = _build(tmp_path, DOC, b"%PDF v1")
    _build_anchors(tmp_path, DOC, first)
    route = _route()
    await _pinning(repo).pin(_point(tmp_path), route, {DOC: first}, at=AT)
    second = _build(tmp_path, DOC, b"%PDF v2")

    await _pinning(repo).pin(_point(tmp_path), replace(route, round=2), {DOC: second}, at=AT)

    assert repo.get_state(tmp_path).pinned[DOC].sha256 == second
    assert _pinned_anchors(tmp_path) is None


async def test__pin__unbuilt_document__keeps_the_anchors_of_its_version(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    sha = _build(tmp_path, DOC, b"%PDF v1")
    _build_anchors(tmp_path, DOC, sha)
    first = _route()
    await _pinning(repo).pin(_point(tmp_path), first, {DOC: sha}, at=AT)
    (tmp_path / "out" / ".build" / DOC / f"{DOC}.anchors.json").unlink()

    await _pinning(repo).pin(_point(tmp_path, unbuilt=(DOC,)), replace(first, round=2), {DOC: sha}, at=AT)

    copied = _pinned_anchors(tmp_path)
    assert copied is not None
    assert copied.pdf_sha256 == sha


async def test__unpin__removes_the_anchors_copy_with_the_version(tmp_path: Path) -> None:
    repo = JsonSignatureRepository()
    route = _route()
    sha = _build(tmp_path, DOC, b"%PDF a")
    _build_anchors(tmp_path, DOC, sha)
    await _pinning(repo).pin(_point(tmp_path), route, {DOC: sha}, at=AT)
    assert (tmp_path / ANCHORS).exists()

    _pinning(repo).unpin(_point(tmp_path), replace(route, docs=(DOC,)))

    assert not (tmp_path / ANCHORS).exists()
