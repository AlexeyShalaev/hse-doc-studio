from __future__ import annotations

import asyncio
import hashlib
import os
import stat
from pathlib import Path

import pytest
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.infra.runner.outputs import collect_outputs
from hse_doc_studio.infra.runner.workspace import BlobCache, BlobIntegrityError, RunnerWorkspaces


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(path: str, data: bytes) -> ManifestFile:
    return ManifestFile(path=path, sha256=_sha(data), size=len(data))


class _Store:
    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = {_sha(v): v for v in blobs.values()}
        self.fetched: list[str] = []

    async def fetch(self, sha: str) -> bytes:
        self.fetched.append(sha)
        return self.blobs[sha]


def _make(tmp_path: Path, store: _Store) -> tuple[BlobCache, RunnerWorkspaces]:
    cache = BlobCache(tmp_path, store.fetch)
    return cache, RunnerWorkspaces(tmp_path, cache)


async def test_sync_copies_and_build_cannot_touch_shared_blob(tmp_path: Path) -> None:
    store = _Store({"a": b"alpha"})
    cache, spaces = _make(tmp_path, store)
    manifest = (_entry("main.tex", b"alpha"),)
    async with spaces.open("p1", manifest) as ws:
        (ws.root / "main.tex").write_bytes(b"poisoned")
    blob = cache.path_of(_sha(b"alpha"))
    assert blob.read_bytes() == b"alpha"
    assert stat.S_IMODE(blob.stat().st_mode) == 0o444
    async with spaces.open("p2", manifest) as ws2:
        assert (ws2.root / "main.tex").read_bytes() == b"alpha"
    async with spaces.open("p1", manifest) as ws3:
        assert (ws3.root / "main.tex").read_bytes() == b"alpha"
        assert (ws3.root / "main.tex").stat().st_ino != blob.stat().st_ino
    assert len(store.fetched) == 1


async def test_incremental_sync_removes_stale_keeps_build(tmp_path: Path) -> None:
    store = _Store({"a": b"a", "b": b"b", "c": b"c"})
    _, spaces = _make(tmp_path, store)
    async with spaces.open("p", (_entry("a.tex", b"a"), _entry("d/b.tex", b"b"))) as ws:
        (ws.root / ".build").mkdir()
        (ws.root / ".build" / "aux").write_text("x")
        (ws.root / "junk.txt").write_text("j")
    async with spaces.open("p", (_entry("a.tex", b"a"), _entry("c.tex", b"c"))) as ws:
        assert not (ws.root / "d").exists()
        assert not (ws.root / "junk.txt").exists()
        assert (ws.root / "c.tex").read_bytes() == b"c"
        assert (ws.root / ".build" / "aux").read_text() == "x"
    assert len(store.fetched) == 3


async def test_symlink_in_workspace_is_replaced(tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    store = _Store({"a": b"a"})
    _, spaces = _make(tmp_path, store)
    manifest = (_entry("sub/a.tex", b"a"),)
    async with spaces.open("p", manifest) as ws:
        (ws.root / "sub" / "a.tex").unlink()
        (ws.root / "sub" / "a.tex").symlink_to(outside)
    async with spaces.open("p", manifest) as ws:
        target = ws.root / "sub" / "a.tex"
        assert not target.is_symlink()
        assert target.read_bytes() == b"a"
    assert outside.read_text() == "secret"
    async with spaces.open("p", manifest) as ws:
        (ws.root / "sub").rename(ws.root / "sub_old")
        (ws.root / "sub").symlink_to(tmp_path)
    async with spaces.open("p", manifest) as ws:
        assert not (ws.root / "sub").is_symlink()
        assert (ws.root / "sub" / "a.tex").read_bytes() == b"a"


async def test_traversal_in_manifest_rejected(tmp_path: Path) -> None:
    _, spaces = _make(tmp_path, _Store({}))
    with pytest.raises(ValueError, match="escapes|project id"):
        async with spaces.open("p", (ManifestFile(path="../x", sha256=_sha(b"x"), size=1),)):
            pass
    with pytest.raises(ValueError, match="escapes|project id"):
        async with spaces.open("../p", ()):
            pass


async def test_corrupted_cache_blob_refetched(tmp_path: Path) -> None:
    store = _Store({"a": b"data"})
    cache, spaces = _make(tmp_path, store)
    manifest = (_entry("a.tex", b"data"),)
    async with spaces.open("p", manifest):
        pass
    blob = cache.path_of(_sha(b"data"))
    blob.chmod(0o644)
    blob.write_bytes(b"rotten")
    async with spaces.open("q", manifest) as ws:
        assert (ws.root / "a.tex").read_bytes() == b"data"
    assert len(store.fetched) == 2


async def test_fetched_blob_must_match_digest(tmp_path: Path) -> None:
    async def liar(_: str) -> bytes:
        return b"other"

    cache = BlobCache(tmp_path, liar)
    with pytest.raises(BlobIntegrityError):
        await cache.ensure(_sha(b"wanted"), 6)
    assert not cache.path_of(_sha(b"wanted")).exists()


async def test_project_lock_serialises_jobs(tmp_path: Path) -> None:
    _, spaces = _make(tmp_path, _Store({}))
    order: list[str] = []

    async def job(name: str) -> None:
        async with spaces.open("p", ()):
            order.append(f"{name}+")
            await asyncio.sleep(0.02)
            order.append(f"{name}-")

    await asyncio.gather(job("a"), job("b"))
    assert order in (["a+", "a-", "b+", "b-"], ["b+", "b-", "a+", "a-"])


async def test_eviction_keeps_recent_and_pinned(tmp_path: Path) -> None:
    store = _Store({"a": b"a" * 10, "b": b"b" * 10, "c": b"c" * 10})
    cache = BlobCache(tmp_path, store.fetch)
    paths = [await cache.ensure(_sha(v)) for v in (b"a" * 10, b"b" * 10, b"c" * 10)]
    for i, p in enumerate(paths):
        os.utime(p, (1000 + i, 1000 + i))
    removed = cache.evict(20, keep=frozenset({_sha(b"a" * 10)}))
    assert removed == 1
    assert paths[0].exists()
    assert not paths[1].exists()
    assert paths[2].exists()


def test_collector_skips_symlinks_unchanged_and_unlisted(tmp_path: Path) -> None:
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(b"secret")
    root = tmp_path / "ws"
    (root / "out").mkdir(parents=True)
    (root / "main.pdf").write_bytes(b"pdf")
    (root / "same.pdf").write_bytes(b"same")
    (root / "notes.txt").write_text("x")
    (root / "link.pdf").symlink_to(secret)
    (root / "evil").symlink_to(tmp_path)
    os.link(secret, root / "hard.pdf")
    (root / "out" / "b.pdf").write_bytes(b"b")
    found = collect_outputs(root, ["*.pdf"], {"same.pdf": _sha(b"same")})
    assert [o.ref.path for o in found] == ["main.pdf", "out/b.pdf"]
    assert found[0].ref.sha256 == _sha(b"pdf")
    assert found[0].ref.size == 3


def test_collector_size_limit(tmp_path: Path) -> None:
    (tmp_path / "big.pdf").write_bytes(b"x" * 10)
    assert collect_outputs(tmp_path, ["*.pdf"], max_file_bytes=5) == ()
