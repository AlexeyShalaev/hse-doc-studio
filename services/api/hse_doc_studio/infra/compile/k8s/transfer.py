"""Вход и выход пода сборки tar-потоком: рабочая папка туда, `.build/<doc_id>` документа обратно."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import IO

_SPOOL_BYTES = 8 * 1024 * 1024
BUILD_DIR = ".build"


class OutputTooLargeError(Exception):
    """Выход сборки больше `max_output_bytes`."""


def pack_workspace(root: Path, build_rel: str) -> tuple[IO[bytes], int]:
    """Tar рабочей папки без чужих `.build/`, без ссылок; режимы и владельцы нормализованы.

    `.build/<doc_id>` этого документа входит: latexmk пересобирает инкрементально, как с docker.
    """
    keep = PurePosixPath(build_rel)
    spool = tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES)  # noqa: SIM115
    with tarfile.open(fileobj=spool, mode="w", format=tarfile.PAX_FORMAT) as tar:
        _add_tree(tar, root, keep)
        for part in _parents(keep):
            if not (root / part).is_dir():
                _add_dir(tar, part.as_posix())
    size = spool.tell()
    spool.seek(0)
    return spool, size


def _add_tree(tar: tarfile.TarFile, root: Path, keep: PurePosixPath) -> None:
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = PurePosixPath(Path(dirpath).relative_to(root).as_posix())
        kept: list[str] = []
        for name in sorted(dirnames):
            rel = rel_dir / name
            if (Path(dirpath) / name).is_symlink() or not _wanted(rel, keep):
                continue
            kept.append(name)
            _add_dir(tar, rel.as_posix())
        dirnames[:] = kept
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if path.is_symlink() or not path.is_file():
                continue
            info = tar.gettarinfo(str(path), arcname=(rel_dir / name).as_posix())
            _normalize(info, 0o644)
            with path.open("rb") as fh:
                tar.addfile(info, fh)


def _wanted(rel: PurePosixPath, keep: PurePosixPath) -> bool:
    """Каталог `.build` берётся только на пути к `keep` и внутри него."""
    if BUILD_DIR not in rel.parts:
        return True
    return rel == keep or keep in rel.parents or rel in keep.parents


def _parents(keep: PurePosixPath) -> list[PurePosixPath]:
    return [*reversed(keep.parents[:-1]), keep]


def _add_dir(tar: tarfile.TarFile, arcname: str) -> None:
    info = tarfile.TarInfo(arcname)
    info.type = tarfile.DIRTYPE
    _normalize(info, 0o755)
    tar.addfile(info)


def _normalize(info: tarfile.TarInfo, mode: int) -> None:
    info.mode = mode
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = int(info.mtime)


class OutputSpool:
    """Приёмник stdout exec с пределом размера; лишнее обрывает exec исключением."""

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._size = 0
        self.file: IO[bytes] = tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES)  # noqa: SIM115

    def write(self, chunk: bytes) -> None:
        self._size += len(chunk)
        if self._size > self._max_bytes:
            raise OutputTooLargeError(f"build output exceeds {self._max_bytes} bytes")
        self.file.write(chunk)

    def close(self) -> None:
        self.file.close()


def extract_build(archive: IO[bytes], root: Path, build_rel: str) -> None:
    """Заменяет `.build/<doc_id>` рабочей папки выходом пода; чужие пути, ссылки и устройства отвергаются."""
    archive.seek(0)
    keep = PurePosixPath(build_rel)
    target = root / build_rel
    with tarfile.open(fileobj=archive, mode="r:") as tar:
        members = []
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise tarfile.OutsideDestinationError(member, member.name)
            if path != keep and keep not in path.parents:
                continue
            if not (member.isfile() or member.isdir()):
                continue
            members.append(member)
        shutil.rmtree(target, ignore_errors=True)
        tar.extractall(root, members=members, filter="data")
    target.mkdir(parents=True, exist_ok=True)
