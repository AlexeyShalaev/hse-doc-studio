"""Том проектов на локальном диске сервера."""

from __future__ import annotations

import errno
import os
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import IO
from uuid import UUID

from hse_doc_studio.core.projects.volume import OpenMode, UnsafePathError

_FLAGS: dict[str, int] = {
    "rb": os.O_RDONLY,
    "wb": os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
    "ab": os.O_WRONLY | os.O_CREAT | os.O_APPEND,
    "r+b": os.O_RDWR,
}
# Безопасный обход через дескрипторы каталогов (openat + O_NOFOLLOW) есть только на POSIX.
# На Windows нет ни O_DIRECTORY/O_NOFOLLOW, ни dir_fd: там путь проверяется покомпонентно по lstat.
_FD_WALK = hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW") and os.open in os.supports_dir_fd
_DIR_FLAGS = (os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW) if _FD_WALK else 0
_BINARY = getattr(os, "O_BINARY", 0)
_FILE_MODE = 0o644
_DIR_MODE = 0o755


def _parse_id(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise UnsafePathError(f"не id проекта: {value!r}") from exc
    if str(parsed) != value:
        raise UnsafePathError(f"id проекта не в каноническом виде: {value!r}")
    return parsed


def _components(relative: str) -> list[str]:
    if not relative or "\x00" in relative or "\\" in relative:
        raise UnsafePathError(f"недопустимый путь: {relative!r}")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in ("", ".", "..") for part in relative.split("/")):
        raise UnsafePathError(f"путь выходит за проект: {relative!r}")
    return list(path.parts)


class LocalDiskProjectVolume:
    def __init__(self, root: Path) -> None:
        self._root = Path(os.path.abspath(root))

    @property
    def root(self) -> Path:
        return self._root

    def path_of(self, project_id: UUID | str) -> Path:
        folder = self._root / str(_parse_id(project_id))
        if folder.is_symlink():
            raise UnsafePathError(f"папка проекта это симлинк: {folder.name}")
        return folder

    def id_of(self, folder: Path) -> UUID:
        absolute = Path(os.path.abspath(folder)) if folder.is_absolute() else None
        if absolute is None or absolute.parent != self._root:
            raise UnsafePathError(f"папка вне тома проектов: {folder}")
        project_id = _parse_id(absolute.name)
        if absolute.is_symlink():
            raise UnsafePathError(f"папка проекта это симлинк: {absolute.name}")
        return project_id

    def resolve_workspace(self, workspace_path: str) -> Path:
        return self.path_of(workspace_path)

    def exists(self, project_id: UUID | str) -> bool:
        folder = self._root / str(_parse_id(project_id))
        return folder.is_dir() and not folder.is_symlink()

    def allocate(self, project_id: UUID | str) -> Path:
        folder = self._root / str(_parse_id(project_id))
        self._root.mkdir(parents=True, exist_ok=True)
        folder.mkdir()
        return folder

    def remove(self, project_id: UUID | str) -> None:
        folder = self._root / str(_parse_id(project_id))
        if folder.is_symlink():
            folder.unlink()
            return
        shutil.rmtree(folder, ignore_errors=False)

    def safe_open(self, folder: Path, relative: str, mode: OpenMode = "rb", *, make_parents: bool = False) -> IO[bytes]:
        self.id_of(folder)
        parts = _components(relative)
        if not _FD_WALK:
            return self._safe_open_by_path(folder, parts, relative, mode, make_parents)
        fds: list[int] = []
        try:
            current = os.open(folder, _DIR_FLAGS)
            fds.append(current)
            for part in parts[:-1]:
                current = self._step(current, part, make_parents)
                fds.append(current)
            fd = self._open_leaf(current, parts[-1], mode)
        except OSError as exc:
            # ELOOP: O_NOFOLLOW наткнулся на симлинк; ENOTDIR: на месте каталога файл или ссылка
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise UnsafePathError(f"симлинк в пути: {relative!r}") from exc
            raise
        finally:
            for opened in fds:
                os.close(opened)
        return os.fdopen(fd, mode)

    @staticmethod
    def _is_link(path: Path) -> bool:
        return path.is_symlink() or os.path.isjunction(path)

    def _safe_open_by_path(
        self, folder: Path, parts: list[str], relative: str, mode: OpenMode, make_parents: bool
    ) -> IO[bytes]:
        """Запасной путь без dir_fd (Windows): ссылки и не-каталоги в цепочке отвергаются по lstat.

        Окно гонки между проверкой и открытием здесь шире, чем у openat; на Windows это принято,
        потому что том проектов принадлежит одному сервисному пользователю.
        """
        current = folder
        for part in parts[:-1]:
            current = self._step_by_path(current / part, relative, make_parents)
        leaf = current / parts[-1]
        if self._is_link(leaf):
            raise UnsafePathError(f"симлинк в пути: {relative!r}")
        if leaf.exists() and not leaf.is_file():
            raise UnsafePathError(f"не обычный файл: {parts[-1]!r}")
        fd = os.open(leaf, _FLAGS[mode] | _BINARY | getattr(os, "O_NOINHERIT", 0), _FILE_MODE)
        return os.fdopen(fd, mode)

    def _step_by_path(self, directory: Path, relative: str, make_parents: bool) -> Path:
        if self._is_link(directory):
            raise UnsafePathError(f"симлинк в пути: {relative!r}")
        if not directory.exists():
            if not make_parents:
                raise FileNotFoundError(errno.ENOENT, "нет каталога", str(directory))
            directory.mkdir()
        elif not directory.is_dir():
            raise UnsafePathError(f"симлинк в пути: {relative!r}")
        return directory

    @staticmethod
    def _step(parent_fd: int, name: str, make_parents: bool) -> int:
        try:
            return os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            if not make_parents:
                raise
            os.mkdir(name, _DIR_MODE, dir_fd=parent_fd)
            return os.open(name, _DIR_FLAGS, dir_fd=parent_fd)

    @staticmethod
    def _open_leaf(parent_fd: int, name: str, mode: str) -> int:
        fd = os.open(name, _FLAGS[mode] | os.O_NOFOLLOW | os.O_CLOEXEC | _BINARY, _FILE_MODE, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise UnsafePathError(f"не обычный файл: {name!r}")
        return fd
