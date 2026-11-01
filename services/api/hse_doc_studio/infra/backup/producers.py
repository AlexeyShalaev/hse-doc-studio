"""Части бэкапа: дамп базы, файлы data_dir, объекты хранилища, выгрузка настроек."""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import stat
import subprocess
import tarfile
import tempfile
import threading
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import structlog
from sqlalchemy.engine import make_url

from hse_doc_studio.core.backup.crypto import EncryptingWriter
from hse_doc_studio.core.backup.entities import PART_DB, PART_FILES, PART_OBJECTS, PART_SETTINGS
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.protocols import IBackupDestinationRepository
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.storage.ports import IObjectStore

logger = structlog.get_logger()

_CHUNK = 1024 * 1024
_STDERR_TAIL = 800
ARC_DATA = "data"
ARC_PROJECTS = "projects_root"


def pg_env(dsn: str) -> tuple[list[str], dict[str, str]]:
    """Параметры подключения для pg_dump и pg_restore из DSN приложения; пароль только через окружение."""
    url = make_url(dsn)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    args: list[str] = []
    if url.host:
        args += ["--host", url.host]
    if url.port:
        args += ["--port", str(url.port)]
    if url.username:
        args += ["--username", url.username]
    if url.password:
        env["PGPASSWORD"] = url.password
    for name, value in url.query.items():
        if name in {"sslmode", "sslrootcert", "sslcert", "sslkey"} and isinstance(value, str):
            env["PG" + name.upper()] = value
    args += ["--dbname", url.database or "postgres"]
    return args, env


def _tail(handle: BinaryIO) -> str:
    handle.seek(0)
    return handle.read().decode(errors="replace").strip()[-_STDERR_TAIL:]


class DbDumpProducer:
    name = PART_DB

    def __init__(self, dsn: str, binary: str, timeout_s: float) -> None:
        self._dsn = dsn
        self._binary = binary
        self._timeout = timeout_s

    async def produce(self, writer: EncryptingWriter) -> dict[str, int]:
        return await asyncio.to_thread(self._run, writer)

    def _run(self, writer: EncryptingWriter) -> dict[str, int]:
        args, env = pg_env(self._dsn)
        command = [self._binary, "--format=custom", "--no-owner", "--no-acl", *args]
        total = 0
        with tempfile.TemporaryFile() as err:
            try:
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=err, env=env)  # noqa: S603
            except OSError as exc:
                raise BackupError(BackupErrorCode.invalid_input, f"cannot start {self._binary}: {exc}") from exc
            assert proc.stdout is not None  # noqa: S101
            timer = threading.Timer(self._timeout, proc.kill)
            timer.start()
            try:
                while chunk := proc.stdout.read(_CHUNK):
                    writer.write(chunk)
                    total += len(chunk)
                code = proc.wait()
            finally:
                timer.cancel()
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
            if code != 0:
                raise BackupError(BackupErrorCode.integrity, f"pg_dump exited with {code}: {_tail(err)}")
        return {"bytes": total}


@dataclass(frozen=True)
class FilesRoot:
    arcname: str
    path: Path
    excluded: frozenset[str] = frozenset()


class _Bounded:
    """Ровно `size` байт из файла: усохший файл добивается нулями, выросший обрезается (заголовок tar уже записан)."""

    def __init__(self, handle: BinaryIO, size: int) -> None:
        self._handle = handle
        self._left = size

    def read(self, n: int = -1) -> bytes:
        if self._left <= 0:
            return b""
        want = self._left if n < 0 else min(n, self._left)
        data = self._handle.read(want)
        if not data:
            data = b"\0" * want
        self._left -= len(data)
        return data


class FilesProducer:
    name = PART_FILES

    def __init__(self, roots: list[FilesRoot]) -> None:
        self._roots = roots

    async def produce(self, writer: EncryptingWriter) -> dict[str, int]:
        return await asyncio.to_thread(self._run, writer)

    def _run(self, writer: EncryptingWriter) -> dict[str, int]:
        counts = {"files": 0, "bytes": 0, "skipped": 0}
        with tarfile.open(fileobj=writer, mode="w|gz", compresslevel=3, format=tarfile.PAX_FORMAT) as tar:  # type: ignore[call-overload]
            for root in self._roots:
                if root.path.is_dir():
                    self._add_tree(tar, root, counts)
        return counts

    def _add_tree(self, tar: tarfile.TarFile, root: FilesRoot, counts: dict[str, int]) -> None:
        for current, dirs, names in os.walk(root.path, followlinks=False):
            here = Path(current)
            rel_dir = here.relative_to(root.path).as_posix()
            dirs[:] = sorted(d for d in dirs if self._keep(root, f"{rel_dir}/{d}".removeprefix("./")))
            if rel_dir != ".":
                self._add_dir(tar, here, f"{root.arcname}/{rel_dir}")
            for name in sorted(names):
                rel = f"{rel_dir}/{name}".removeprefix("./")
                if self._keep(root, rel):
                    self._add_entry(tar, here / name, f"{root.arcname}/{rel}", counts)

    @staticmethod
    def _keep(root: FilesRoot, rel: str) -> bool:
        return not any(rel == ex or rel.startswith(ex + "/") for ex in root.excluded)

    @staticmethod
    def _add_dir(tar: tarfile.TarFile, path: Path, arcname: str) -> None:
        try:
            info = tar.gettarinfo(str(path), arcname)
        except OSError:
            return
        tar.addfile(info)

    @staticmethod
    def _add_entry(tar: tarfile.TarFile, path: Path, arcname: str, counts: dict[str, int]) -> None:
        try:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                tar.addfile(tar.gettarinfo(str(path), arcname))
                return
            if not stat.S_ISREG(mode):
                counts["skipped"] += 1
                return
            with path.open("rb") as handle:
                info = tar.gettarinfo(arcname=arcname, fileobj=handle)
                tar.addfile(info, _Bounded(handle, info.size))
        except (FileNotFoundError, PermissionError):
            # Файл исчез или недоступен во время обхода: журналы и временные файлы живут своей жизнью.
            counts["skipped"] += 1
            return
        counts["files"] += 1
        counts["bytes"] += info.size


class ObjectsProducer:
    name = PART_OBJECTS

    def __init__(self, store: IObjectStore) -> None:
        self._store = store

    async def produce(self, writer: EncryptingWriter) -> dict[str, int]:
        counts = {"objects": 0, "bytes": 0}
        gz = gzip.GzipFile(fileobj=writer, mode="wb", compresslevel=3)
        try:
            for info in await self._store.list_objects(""):
                header = tarfile.TarInfo(info.key)
                header.size = info.size
                header.mtime = int(info.last_modified.timestamp())
                header.mode = 0o600
                await asyncio.to_thread(gz.write, header.tobuf(tarfile.PAX_FORMAT))
                written = 0
                async for chunk in self._store.stream(info.key):
                    written += len(chunk)
                    if written > info.size:
                        break
                    await asyncio.to_thread(gz.write, chunk)
                if written != info.size:
                    raise BackupError(BackupErrorCode.integrity, f"object {info.key} changed during the backup")
                padding = -info.size % tarfile.BLOCKSIZE
                if padding:
                    await asyncio.to_thread(gz.write, b"\0" * padding)
                counts["objects"] += 1
                counts["bytes"] += info.size
            await asyncio.to_thread(gz.write, b"\0" * (tarfile.BLOCKSIZE * 2))
        finally:
            await asyncio.to_thread(gz.close)
        return counts


class SettingsProducer:
    """Выгрузка для человека: настройки установки без секретов и назначения без ключей."""

    name = PART_SETTINGS

    def __init__(self, settings: IInstanceSettingsRepository, destinations: IBackupDestinationRepository) -> None:
        self._settings = settings
        self._destinations = destinations

    async def produce(self, writer: EncryptingWriter) -> dict[str, int]:
        values: Mapping[str, object] = await self._settings.get_all()
        listed = await self._destinations.list_all()
        body = {
            "instance_settings": {k: ("<secret>" if v is True and "secret" in k else v) for k, v in values.items()},
            "destinations": [
                {
                    "name": d.spec.name,
                    "kind": d.spec.kind.value,
                    "endpoint": d.spec.endpoint,
                    "bucket": d.spec.bucket,
                    "prefix": d.spec.prefix,
                    "is_default": d.is_default,
                }
                for d in listed
            ],
        }
        data = json.dumps(body, ensure_ascii=False, indent=2, default=str).encode()
        await asyncio.to_thread(writer.write, data)
        return {"keys": len(values)}


def excluded_names(data_dir: Path, extra: Collection[Path]) -> frozenset[str]:
    """Относительные пути внутри data_dir, которые бэкап не берёт: служебные каталоги и сами назначения."""
    names = {"tmp", "jobs", "backups"}
    resolved = data_dir.resolve()
    for path in extra:
        try:
            names.add(path.resolve().relative_to(resolved).as_posix())
        except ValueError:
            continue
    return frozenset(n for n in names if n and n != ".")
