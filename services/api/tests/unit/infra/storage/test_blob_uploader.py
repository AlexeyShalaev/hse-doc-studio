from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.storage import ChecksumMismatchError, blob_key
from hse_doc_studio.core.storage.manifest import (
    ManifestFileChangedError,
    ManifestFileMissingError,
    ManifestFileTooLargeError,
    ManifestLimits,
    ManifestTooLargeError,
    ManifestUnsafePathError,
)
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.infra.storage import blob_uploader
from hse_doc_studio.infra.storage.blob_uploader import ManifestBlobUploader
from hse_doc_studio.infra.storage.blobs import ObjectBlobStore
from hse_doc_studio.infra.storage.fs import FsObjectStore

from tests.fakes.blob_registry import InMemoryBlobRegistry

_PAST = 10_000_000_000  # на 10 секунд вперёд: свежие файлы теста уже «давно не менялись»


class CountingBlobs(ObjectBlobStore):
    def __init__(self, store: FsObjectStore) -> None:
        super().__init__(store)
        self.puts = 0

    async def put(self, source, *, sha256=None):  # type: ignore[no-untyped-def]
        self.puts += 1
        return await super().put(source, sha256=sha256)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class World:
    def __init__(self, tmp_path: Path, *, stable: bool = True) -> None:
        self.volume = LocalDiskProjectVolume(tmp_path / "projects")
        self.project_id: UUID = uuid4()
        self.folder = self.volume.allocate(self.project_id)
        self.objects = FsObjectStore(tmp_path / "objects", max_object_bytes=10 * 1024 * 1024)
        self.blobs = CountingBlobs(self.objects)
        self.registry = InMemoryBlobRegistry()
        clock = (lambda: time.time_ns() + _PAST) if stable else time.time_ns
        self.uploader = ManifestBlobUploader(self.volume, self.registry, self.blobs, clock_ns=clock)

    def write(self, name: str, data: bytes) -> None:
        target = self.folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    async def ensure(self, *paths: str, limits: ManifestLimits | None = None):  # type: ignore[no-untyped-def]
        return await self.uploader.ensure(self.project_id, self.folder, list(paths), limits)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


async def test__ensure__new_files__manifest_has_hashes_and_blobs_are_stored(world: World) -> None:
    world.write("main.tex", b"hello")
    world.write("img/a.png", b"png-bytes")

    manifest = await world.ensure("main.tex", "img/a.png")

    assert [(f.path, f.sha256, f.size) for f in manifest] == [
        ("main.tex", sha(b"hello"), 5),
        ("img/a.png", sha(b"png-bytes"), 9),
    ]
    assert await world.objects.get(blob_key(sha(b"hello"))) == b"hello"
    assert set(world.registry.blobs) == {sha(b"hello"), sha(b"png-bytes")}


async def test__ensure__unchanged_folder__nothing_uploaded_and_files_not_read(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.write("main.tex", b"hello")
    world.write("refs.bib", b"@book{}")
    first = await world.ensure("main.tex", "refs.bib")
    puts = world.blobs.puts

    def forbidden(*_args: object) -> object:
        raise AssertionError("файл перечитан, хотя кэш верен")

    monkeypatch.setattr(blob_uploader, "measure", forbidden)
    second = await world.ensure("main.tex", "refs.bib")

    assert second == first
    assert world.blobs.puts == puts


async def test__ensure__changed_file__new_hash_and_only_it_uploaded(world: World) -> None:
    world.write("main.tex", b"hello")
    world.write("refs.bib", b"@book{}")
    await world.ensure("main.tex", "refs.bib")
    puts = world.blobs.puts

    world.write("main.tex", b"hello, world")
    manifest = await world.ensure("main.tex", "refs.bib")

    assert manifest[0].sha256 == sha(b"hello, world")
    assert world.blobs.puts == puts + 1


async def test__ensure__same_size_new_content_with_new_mtime__rehashed(world: World) -> None:
    world.write("main.tex", b"aaaa")
    await world.ensure("main.tex")
    world.write("main.tex", b"bbbb")
    os.utime(world.folder / "main.tex", ns=(1, 1))

    manifest = await world.ensure("main.tex")

    assert manifest[0].sha256 == sha(b"bbbb")


async def test__ensure__same_content_twice__single_blob(world: World) -> None:
    world.write("a.txt", b"same")
    world.write("b.txt", b"same")

    manifest = await world.ensure("a.txt", "b.txt")

    assert manifest[0].sha256 == manifest[1].sha256
    assert world.blobs.puts == 1


async def test__ensure__freshly_modified_file__not_trusted_by_cache(tmp_path: Path) -> None:
    world = World(tmp_path, stable=False)
    world.write("main.tex", b"hello")

    await world.ensure("main.tex")

    assert world.registry.cache == {}


async def test__ensure__blob_in_registry__not_uploaded_again(world: World) -> None:
    world.write("main.tex", b"hello")
    await world.ensure("main.tex")
    world.registry.cache.clear()
    puts = world.blobs.puts

    await world.ensure("main.tex")

    assert world.blobs.puts == puts


@pytest.mark.parametrize("path", ["../secret", "a/../../secret", "/etc/passwd", "a\\b", "", "C:/x"])
async def test__ensure__path_escaping_folder__refused(world: World, path: str) -> None:
    with pytest.raises(ManifestUnsafePathError):
        await world.ensure(path)


async def test__ensure__symlink_file__refused(world: World, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (world.folder / "link.txt").symlink_to(outside)

    with pytest.raises(ManifestUnsafePathError):
        await world.ensure("link.txt")


async def test__ensure__symlinked_parent_dir__refused(world: World, tmp_path: Path) -> None:
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "x.txt").write_text("secret")
    (world.folder / "dir").symlink_to(tmp_path / "outside")

    with pytest.raises(ManifestUnsafePathError):
        await world.ensure("dir/x.txt")


async def test__ensure__missing_file__typed_error(world: World) -> None:
    with pytest.raises(ManifestFileMissingError):
        await world.ensure("nope.tex")


async def test__ensure__file_over_limit__typed_error_and_nothing_uploaded(world: World) -> None:
    world.write("small.txt", b"ok")
    world.write("big.bin", b"x" * 100)

    with pytest.raises(ManifestFileTooLargeError) as caught:
        await world.ensure("small.txt", "big.bin", limits=ManifestLimits(max_file_bytes=50, max_job_bytes=1000))

    assert (caught.value.path, caught.value.size, caught.value.limit) == ("big.bin", 100, 50)
    assert world.blobs.puts == 0


async def test__ensure__total_over_limit__typed_error(world: World) -> None:
    world.write("a.bin", b"x" * 60)
    world.write("b.bin", b"y" * 60)

    with pytest.raises(ManifestTooLargeError):
        await world.ensure("a.bin", "b.bin", limits=ManifestLimits(max_file_bytes=100, max_job_bytes=100))


async def test__ensure__file_changed_while_uploading__typed_error(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.write("main.tex", b"hello")

    async def mismatch(*_args: object, **_kwargs: object) -> object:
        raise ChecksumMismatchError("changed")

    monkeypatch.setattr(world.blobs, "put", mismatch)

    with pytest.raises(ManifestFileChangedError):
        await world.ensure("main.tex")
