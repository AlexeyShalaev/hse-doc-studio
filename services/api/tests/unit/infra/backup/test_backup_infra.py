from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path

import pytest
from hse_doc_studio.api.config.backups import BackupsConfig
from hse_doc_studio.api.config.storage import StorageConfig
from hse_doc_studio.core.backup.crypto import DecryptingReader, EncryptingWriter
from hse_doc_studio.core.backup.entities import DestinationKind, DestinationSecrets, DestinationSpec
from hse_doc_studio.core.backup.errors import BackupError
from hse_doc_studio.infra.backup.pgtools import resolve_binary
from hse_doc_studio.infra.backup.producers import (
    FilesProducer,
    FilesRoot,
    ObjectsProducer,
    excluded_names,
    pg_env,
)
from hse_doc_studio.infra.backup.restore_target import RestoreTarget
from hse_doc_studio.infra.backup.stores import BackupStoreFactory
from hse_doc_studio.infra.storage.fs import FsObjectStore

KEY = os.urandom(32)


async def _seal(producer: FilesProducer | ObjectsProducer) -> bytes:
    sink = io.BytesIO()
    writer = EncryptingWriter(sink, KEY)
    await producer.produce(writer)
    writer.close()
    return sink.getvalue()


def _plain(blob: bytes) -> io.BytesIO:
    return io.BytesIO(DecryptingReader(io.BytesIO(blob), KEY).read())


def _target(tmp_path: Path, store: FsObjectStore | None = None) -> RestoreTarget:
    return RestoreTarget(
        None,  # type: ignore[arg-type]
        "postgresql://u:p@h/db",
        tmp_path / "data",
        tmp_path / "data" / "projects",
        store or FsObjectStore(tmp_path / "objects", max_object_bytes=1 << 30),
    )


async def test__files__roundtrip_preserves_tree_symlinks_and_skips_excluded(tmp_path: Path) -> None:
    data = tmp_path / "src"
    (data / "projects" / "p1" / ".hse-studio").mkdir(parents=True)
    (data / "projects" / "p1" / "main.tex").write_text("текст проекта", encoding="utf-8", newline="\n")
    (data / "projects" / "p1" / ".hse-studio" / "project.json").write_text("{}", encoding="utf-8", newline="\n")
    (data / "users" / "h").mkdir(parents=True)
    (data / "users" / "h" / "role.json").write_text("[1]", encoding="utf-8", newline="\n")
    (data / "gnupg").mkdir()
    (data / "gnupg" / "pubring.kbx").write_bytes(b"\x00\x01")
    (data / "tmp").mkdir()
    (data / "tmp" / "scratch").write_text("temp", encoding="utf-8", newline="\n")
    (data / "jobs").mkdir()
    (data / "jobs" / "log").write_text("log", encoding="utf-8", newline="\n")
    (data / "backups" / "local").mkdir(parents=True)
    (data / "backups" / "local" / "old.enc").write_text("old backup", encoding="utf-8", newline="\n")
    (data / "link").symlink_to("projects/p1/main.tex")
    (data / "empty-dir").mkdir()

    producer = FilesProducer([FilesRoot("data", data, excluded_names(data, [data / "backups"]))])
    blob = await _seal(producer)

    target = _target(tmp_path)
    count = await target.restore_files(_plain(blob), move_existing=False, stamp="s")
    restored = tmp_path / "data"
    assert (restored / "projects" / "p1" / "main.tex").read_text(encoding="utf-8") == "текст проекта"
    assert (restored / "projects" / "p1" / ".hse-studio" / "project.json").exists()
    assert (restored / "gnupg" / "pubring.kbx").read_bytes() == b"\x00\x01"
    assert (restored / "users" / "h" / "role.json").exists()
    assert (restored / "empty-dir").is_dir()
    assert (restored / "link").is_symlink()
    for skipped in ("tmp", "jobs", "backups"):
        assert not (restored / skipped).exists()
    assert count == 4


async def test__files__vanishing_file_is_skipped_not_fatal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "src"
    data.mkdir()
    (data / "a.txt").write_text("a", encoding="utf-8", newline="\n")
    producer = FilesProducer([FilesRoot("data", data)])
    original = Path.lstat

    def flaky(self: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if self.name == "a.txt":
            raise FileNotFoundError(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", flaky)
    notes = await producer.produce(EncryptingWriter(io.BytesIO(), KEY))
    assert notes["skipped"] == 1


async def test__files__second_root_outside_data_dir(tmp_path: Path) -> None:
    projects = tmp_path / "vol"
    (projects / "p").mkdir(parents=True)
    (projects / "p" / "f.txt").write_text("x", encoding="utf-8", newline="\n")
    blob = await _seal(FilesProducer([FilesRoot("data", tmp_path / "missing"), FilesRoot("projects_root", projects)]))
    target = _target(tmp_path)
    await target.restore_files(_plain(blob), move_existing=False, stamp="s")
    assert (tmp_path / "data" / "projects" / "p" / "f.txt").read_text(encoding="utf-8") == "x"


async def test__files__restore_moves_existing_instead_of_deleting(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / "projects" / "new").mkdir(parents=True)
    (src / "projects" / "new" / "f").write_text("new", encoding="utf-8", newline="\n")
    blob = await _seal(FilesProducer([FilesRoot("data", src)]))
    existing = tmp_path / "data" / "projects" / "old"
    existing.mkdir(parents=True)
    (existing / "f").write_text("old", encoding="utf-8", newline="\n")
    await _target(tmp_path).restore_files(_plain(blob), move_existing=True, stamp="STAMP")
    assert (tmp_path / "data" / "projects.before-restore-STAMP" / "old" / "f").read_text(encoding="utf-8") == "old"
    assert (tmp_path / "data" / "projects" / "new" / "f").read_text(encoding="utf-8") == "new"
    assert not (tmp_path / "data" / "projects" / "old").exists()


async def test__files__restore_rejects_path_traversal_and_escaping_links(tmp_path: Path) -> None:
    sink = io.BytesIO()
    with tarfile.open(fileobj=sink, mode="w|gz") as tar:
        info = tarfile.TarInfo("data/../../escaped.txt")
        info.size = 3
        tar.addfile(info, io.BytesIO(b"bad"))
    writer_sink = io.BytesIO()
    writer = EncryptingWriter(writer_sink, KEY)
    writer.write(sink.getvalue())
    writer.close()
    with pytest.raises(tarfile.TarError):
        await _target(tmp_path).restore_files(_plain(writer_sink.getvalue()), move_existing=False, stamp="s")
    assert not (tmp_path / "escaped.txt").exists()
    assert not (tmp_path.parent / "escaped.txt").exists()


async def test__objects__roundtrip_through_store(tmp_path: Path) -> None:
    source = FsObjectStore(tmp_path / "src", max_object_bytes=1 << 30)
    payloads = {"blobs/ab/" + "ab" * 32: os.urandom(3000), "artifacts/doc.pdf": b"%PDF-1.7 body", "empty": b""}
    for key, body in payloads.items():
        await source.put(key, body)
    blob = await _seal(ObjectsProducer(source))
    dest = FsObjectStore(tmp_path / "dst", max_object_bytes=1 << 30)
    count = await _target(tmp_path, dest).restore_objects(_plain(blob))
    assert count == 3
    for key, body in payloads.items():
        assert await dest.get(key) == body


def test__store_factory__local_path_cannot_escape_root(tmp_path: Path) -> None:
    factory = BackupStoreFactory(BackupsConfig(local_root=tmp_path / "root"), StorageConfig(), tmp_path)
    (tmp_path / "root").mkdir()
    (tmp_path / "outside").mkdir()
    (tmp_path / "root" / "link").symlink_to(tmp_path / "outside")
    assert factory.local_path("disk/a") == (tmp_path / "root" / "disk" / "a").resolve()
    for bad in ("../outside", "link", "link/x", ""):
        with pytest.raises(BackupError):
            factory.local_path(bad)
    spec = DestinationSpec("l", DestinationKind.local, local_path="link/x")
    with pytest.raises(BackupError):
        factory.open(spec, DestinationSecrets())


def test__store_factory__is_primary_matches_bucket_and_endpoint_or_same_volume(tmp_path: Path) -> None:
    primary = StorageConfig(bucket="studio", endpoint="http://minio:9000/")
    factory = BackupStoreFactory(BackupsConfig(local_root=tmp_path / "b"), primary, tmp_path)
    same = DestinationSpec("s", DestinationKind.s3, endpoint="http://MINIO:9000", bucket="studio")
    other_bucket = DestinationSpec("s", DestinationKind.s3, endpoint="http://minio:9000", bucket="hse-backups")
    other_host = DestinationSpec("s", DestinationKind.s3, endpoint="http://backup-minio:9000", bucket="studio")
    assert factory.is_primary(same)
    assert not factory.is_primary(other_bucket)
    assert not factory.is_primary(other_host)
    assert factory.is_primary(DestinationSpec("l", DestinationKind.local, local_path="x"))


def test__pg_env__password_only_in_environment() -> None:
    args, env = pg_env("postgresql+asyncpg://studio:s3cr3t@db.example:5433/studio?sslmode=require")
    assert "s3cr3t" not in " ".join(args)
    assert env["PGPASSWORD"] == "s3cr3t"
    assert env["PGSSLMODE"] == "require"
    assert args[-2:] == ["--dbname", "studio"]
    assert args[:2] == ["--host", "db.example"]
    assert "5433" in args


def test__resolve_binary__prefers_matching_major_and_keeps_custom(tmp_path: Path) -> None:
    (tmp_path / "16" / "bin").mkdir(parents=True)
    (tmp_path / "16" / "bin" / "pg_dump").write_text("", encoding="utf-8", newline="\n")
    assert resolve_binary("pg_dump", 16, lib=tmp_path) == str(tmp_path / "16" / "bin" / "pg_dump")
    assert resolve_binary("pg_dump", 15, lib=tmp_path) == "pg_dump"
    assert resolve_binary("/opt/pg/bin/pg_dump", 16, lib=tmp_path) == "/opt/pg/bin/pg_dump"
    assert resolve_binary("pg_dump", None, lib=tmp_path) == "pg_dump"


def test__excluded_names__relative_to_data_dir(tmp_path: Path) -> None:
    data = tmp_path / "data"
    names = excluded_names(data, [data / "storage" / "objects", tmp_path / "elsewhere"])
    assert names == {"tmp", "jobs", "backups", "storage/objects"}
