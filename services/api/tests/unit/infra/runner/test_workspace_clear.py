"""Замер и очистка кэша раннера (S9 `storage-cleanup.md`): свежее и занятое сборкой остаётся, выгрузка цела."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.infra.runner.workspace import BlobCache, RunnerWorkspaces


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _entry(path: str, data: bytes) -> ManifestFile:
    return ManifestFile(path=path, sha256=_sha(data), size=len(data))


class _Store:
    def __init__(self, *blobs: bytes) -> None:
        self.blobs = {_sha(v): v for v in blobs}
        self.fetched: list[str] = []

    async def fetch(self, sha: str) -> bytes:
        self.fetched.append(sha)
        return self.blobs[sha]


def _age(path: Path, seconds: float) -> None:
    then = time.time() - seconds
    os.utime(path, (then, then))


async def test__blob_cache__usage_counts_blobs_without_temp_files(tmp_path: Path) -> None:
    store = _Store(b"alpha", b"beta!")
    cache = BlobCache(tmp_path, store.fetch)
    for sha in store.blobs:
        await cache.ensure(sha)
    temp = cache.path_of(_sha(b"alpha")).with_name(".tmp-abc")
    temp.write_bytes(b"partial")

    usage = await cache.usage()

    assert (usage.bytes, usage.count) == (10, 2)


async def test__blob_cache__clear_removes_idle_blobs_and_keeps_fresh(tmp_path: Path) -> None:
    store = _Store(b"old-blob", b"fresh")
    cache = BlobCache(tmp_path, store.fetch)
    old, fresh = _sha(b"old-blob"), _sha(b"fresh")
    await cache.ensure(old)
    await cache.ensure(fresh)
    _age(cache.path_of(old), 3600)

    freed = await cache.clear()

    assert freed == len(b"old-blob")
    assert not cache.path_of(old).exists()
    assert cache.path_of(fresh).read_bytes() == b"fresh"


async def test__blob_cache__clear_spares_blob_handed_out_by_ensure(tmp_path: Path) -> None:
    store = _Store(b"data")
    cache = BlobCache(tmp_path, store.fetch)
    sha = _sha(b"data")
    await cache.ensure(sha)
    _age(cache.path_of(sha), 3600)

    # Сборка берёт блоб из кэша: `ensure` трогает его, и очистка видит его свежим.
    path = await cache.ensure(sha)
    freed = await cache.clear()

    assert freed == 0
    assert path.read_bytes() == b"data"
    assert store.fetched == [sha]


async def test__blob_cache__clear_skips_blob_under_ensure_lock(tmp_path: Path) -> None:
    store = _Store(b"data")
    cache = BlobCache(tmp_path, store.fetch)
    sha = _sha(b"data")
    await cache.ensure(sha)

    async with cache._locks[sha]:  # `ensure` проверяет блоб прямо сейчас
        freed = await cache.clear(min_idle_s=0)

    assert freed == 0
    assert cache.path_of(sha).exists()
    assert await cache.clear(min_idle_s=0) == len(b"data")


async def test__workspaces__usage_and_clear_skip_busy_project_and_keep_outputs(tmp_path: Path) -> None:
    store = _Store(b"alpha", b"beta")
    cache = BlobCache(tmp_path, store.fetch)
    spaces = RunnerWorkspaces(tmp_path, cache)
    async with spaces.open("idle", (_entry("main.tex", b"alpha"),)) as ws:
        (ws.root / ".build").mkdir()
        (ws.root / ".build" / "main.pdf").write_bytes(b"x" * 100)
    outputs = tmp_path / "outputs" / "job-1" / "0" / "main.pdf"
    outputs.parent.mkdir(parents=True)
    outputs.write_bytes(b"pdf")

    async with spaces.open("busy", (_entry("main.tex", b"beta"),)) as busy:
        usage = await spaces.usage()
        freed = await spaces.clear()
        # Сборка, идущая в занятой папке, ничего не теряет.
        assert (busy.root / "main.tex").read_bytes() == b"beta"

    assert (usage.count, usage.busy) == (2, 1)
    assert usage.bytes == len(b"alpha") + 100 + len(b"beta")
    assert freed == len(b"alpha") + 100
    assert not (tmp_path / "workspaces" / "idle").exists()
    assert (tmp_path / "workspaces" / "busy" / "main.tex").exists()
    assert outputs.read_bytes() == b"pdf"
    assert (await spaces.usage()).busy == 0


async def test__workspaces__project_opened_after_clear_is_rebuilt_from_cache(tmp_path: Path) -> None:
    store = _Store(b"alpha")
    cache = BlobCache(tmp_path, store.fetch)
    spaces = RunnerWorkspaces(tmp_path, cache)
    manifest = (_entry("main.tex", b"alpha"),)
    async with spaces.open("p", manifest):
        pass

    assert await spaces.clear() == len(b"alpha")
    async with spaces.open("p", manifest) as ws:
        assert (ws.root / "main.tex").read_bytes() == b"alpha"
    assert len(store.fetched) == 1


async def test__workspaces__clear_removes_stray_file(tmp_path: Path) -> None:
    store = _Store()
    spaces = RunnerWorkspaces(tmp_path, BlobCache(tmp_path, store.fetch))
    (tmp_path / "workspaces" / "stray").write_bytes(b"12345")

    assert await spaces.clear() == 5
    assert list((tmp_path / "workspaces").iterdir()) == []
