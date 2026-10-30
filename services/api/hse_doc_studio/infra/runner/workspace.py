"""Рабочие папки раннера: кэш блобов по sha256 и материализация манифеста копиями.

Кэш общий для всех проектов, поэтому сборка не должна иметь возможность его менять: файлы кэша
только для чтения (0444), в рабочую папку блоб попадает копией (не жёсткой ссылкой), а хеш
сверяется и при скачивании, и при каждой выдаче из кэша. Рабочая папка проекта живёт между
задачами (тёплая), поэтому перед сборкой каждый файл сверяется с манифестом заново: прошлая
сборка могла его изменить, подменить ссылкой или удалить.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import shutil
import stat
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.jobs.files import ManifestFile, validate_relative_posix

BlobFetcher = Callable[[str], Awaitable[bytes]]

# Эти поддеревья сборка пишет сама, синхронизация их не трогает.
PRESERVED_PREFIXES: tuple[str, ...] = (".build/",)

_CHUNK = 1024 * 1024
_SHA_LEN = 64


class BlobIntegrityError(Exception):
    """Скачанные байты не совпали с заявленными sha256 или размером."""


class WorkspaceStuckError(Exception):
    """В рабочей папке остался каталог, который не удалить (чужой владелец): папку нужно создать заново."""


def _tree_size(path: Path) -> int:
    total = 0
    for current, _, files in os.walk(path, followlinks=False):
        for name in files:
            with contextlib.suppress(OSError):
                total += (Path(current) / name).lstat().st_size
    return total


def _is_sha256(value: str) -> bool:
    return len(value) == _SHA_LEN and all(c in "0123456789abcdef" for c in value)


def file_sha256(path: Path) -> str:
    """Хеш обычного файла; ссылку не открывает."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f"not a regular file: {path}")
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as handle:
            for chunk in iter(lambda: handle.read(_CHUNK), b""):
                digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.close(fd)


class BlobCache:
    """Содержимое по sha256 в `<root>/blobs/<aa>/<sha>`, режим 0444."""

    def __init__(self, root: Path, fetch: BlobFetcher) -> None:
        self._root = root / "blobs"
        self._fetch = fetch
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._root.mkdir(parents=True, exist_ok=True)

    def path_of(self, sha256: str) -> Path:
        if not _is_sha256(sha256):
            raise ValueError(f"bad sha256: {sha256!r}")
        return self._root / sha256[:2] / sha256

    async def ensure(self, sha256: str, size: int | None = None) -> Path:
        """Путь к проверенному блобу; битый или отсутствующий докачивается."""
        target = self.path_of(sha256)
        async with self._locks[sha256]:
            if await asyncio.to_thread(self._is_valid, target, sha256):
                await asyncio.to_thread(self._touch, target)
                return target
            data = await self._fetch(sha256)
            if (size is not None and len(data) != size) or hashlib.sha256(data).hexdigest() != sha256:
                raise BlobIntegrityError(f"blob {sha256} does not match its digest")
            await asyncio.to_thread(self._store, target, data)
            return target

    @staticmethod
    def _is_valid(path: Path, sha256: str) -> bool:
        try:
            return file_sha256(path) == sha256
        except OSError:
            return False

    @staticmethod
    def _touch(path: Path) -> None:
        with contextlib.suppress(OSError):
            os.utime(path)

    @staticmethod
    def _store(target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".tmp-{uuid.uuid4().hex[:12]}")
        try:
            tmp.write_bytes(data)
            tmp.chmod(0o444)
            os.replace(tmp, target)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise

    def evict(self, max_bytes: int, keep: frozenset[str] = frozenset()) -> int:
        """Удаляет давно не использованные блобы, пока кэш не уложится в предел; возвращает число удалённых."""
        entries: list[tuple[float, int, Path, str]] = []
        total = 0
        for path in self._root.glob("*/*"):
            if path.name.startswith("."):
                continue
            try:
                info = path.lstat()
            except OSError:
                continue
            total += info.st_size
            entries.append((info.st_mtime, info.st_size, path, path.name))
        removed = 0
        for _, size, path, name in sorted(entries):
            if total <= max_bytes:
                break
            if name in keep:
                continue
            with contextlib.suppress(OSError):
                path.unlink()
                total -= size
                removed += 1
        return removed


@dataclass(frozen=True)
class Workspace:
    """Материализованный проект: корень и хеши файлов манифеста на момент синхронизации."""

    root: Path
    baseline: dict[str, str]


class RunnerWorkspaces:
    """Тёплые рабочие папки по проектам; одновременно в папке работает одна задача."""

    def __init__(self, root: Path, cache: BlobCache, max_bytes: int | None = None) -> None:
        self._root = root / "workspaces"
        self._cache = cache
        self._max_bytes = max_bytes
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._root.mkdir(parents=True, exist_ok=True)

    @contextlib.asynccontextmanager
    async def open(self, project_id: str, manifest: tuple[ManifestFile, ...]) -> AsyncIterator[Workspace]:
        """Берёт блокировку проекта, приводит папку к манифесту и держит замок до выхода из блока."""
        if not project_id or "/" in project_id or "\\" in project_id or project_id in {".", ".."}:
            raise ValueError(f"bad project id: {project_id!r}")
        async with self._locks[project_id]:
            root = self._root / project_id
            root.mkdir(parents=True, exist_ok=True)
            try:
                try:
                    baseline = await self._sync(root, manifest)
                except (WorkspaceStuckError, PermissionError):
                    # Сборка оставила то, что раннер не может убрать: начинаем с чистой папки.
                    await asyncio.to_thread(self._reset, root)
                    baseline = await self._sync(root, manifest)
                yield Workspace(root=root, baseline=baseline)
            finally:
                # Время последнего использования для вытеснения по LRU.
                with contextlib.suppress(OSError):
                    os.utime(root)

    def _inventory(self) -> tuple[list[tuple[float, int, Path]], int]:
        entries: list[tuple[float, int, Path]] = []
        total = 0
        for path in self._root.iterdir():
            try:
                mtime = path.lstat().st_mtime
            except OSError:
                continue
            size = _tree_size(path)
            total += size
            entries.append((mtime, size, path))
        return entries, total

    def evict(self, keep: frozenset[str] = frozenset()) -> int:
        """Удаляет давно не использованные папки проектов, пока все вместе не уложатся в предел.

        Занятые (замок взят) и перечисленные в `keep` не трогаются; возвращает число удалённых.
        """
        if self._max_bytes is None:
            return 0
        entries, total = self._inventory()
        removed = 0
        for _, size, path in sorted(entries):
            if total <= self._max_bytes:
                break
            lock = self._locks.get(path.name)
            if path.name in keep or (lock is not None and lock.locked()):
                continue
            shutil.rmtree(path, ignore_errors=True)
            if path.exists():
                continue
            total -= size
            removed += 1
        return removed

    @staticmethod
    def _reset(root: Path) -> None:
        shutil.rmtree(root, ignore_errors=True)
        if root.exists():
            raise WorkspaceStuckError(root.name)
        root.mkdir(parents=True, exist_ok=True)

    async def _sync(self, root: Path, manifest: tuple[ManifestFile, ...]) -> dict[str, str]:
        wanted: dict[str, ManifestFile] = {}
        for entry in manifest:
            validate_relative_posix(entry.path)
            if entry.sha256 is None or entry.size is None:
                raise ValueError(f"manifest entry {entry.path!r} needs sha256 and size")
            wanted[entry.path] = entry
        await asyncio.to_thread(self._prune, root, frozenset(wanted))
        baseline: dict[str, str] = {}
        for path, entry in wanted.items():
            assert entry.sha256 is not None  # noqa: S101
            baseline[path] = entry.sha256
            if await asyncio.to_thread(self._is_current, root, path, entry.sha256):
                continue
            blob = await self._cache.ensure(entry.sha256, entry.size)
            await asyncio.to_thread(self._place, root, path, blob, entry.sha256)
        return baseline

    @staticmethod
    def _is_current(root: Path, rel: str, sha256: str) -> bool:
        target = root / rel
        try:
            if not stat.S_ISREG(target.lstat().st_mode):
                return False
            if any(stat.S_ISLNK((root / p).lstat().st_mode) for p in _parents(rel)):
                return False
            return file_sha256(target) == sha256
        except OSError:
            return False

    @staticmethod
    def _place(root: Path, rel: str, blob: Path, sha256: str) -> None:
        for parent in _parents(rel):
            _ensure_real_dir(root / parent)
        target = root / rel
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target, ignore_errors=True)
            if target.exists():
                raise WorkspaceStuckError(rel)
        tmp = target.with_name(f".tmp-{uuid.uuid4().hex[:12]}")
        try:
            shutil.copyfile(blob, tmp)
            tmp.chmod(0o644)
            # Копия проверяется ещё раз: кэш мог измениться между проверкой и копированием.
            if file_sha256(tmp) != sha256:
                raise BlobIntegrityError(f"copy of {sha256} differs from the cache")
            # replace заменяет и сам симлинк, не идя по нему.
            os.replace(tmp, target)
        except BaseException:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise

    @staticmethod
    def _prune(root: Path, wanted: frozenset[str]) -> None:
        """Убирает всё, чего нет в манифесте, кроме поддеревьев сборки; ссылки удаляет, не следуя им."""
        for current, dirs, files in os.walk(root, followlinks=False):
            base = Path(current)
            rel_base = base.relative_to(root).as_posix()
            prefix = "" if rel_base == "." else rel_base + "/"
            dirs[:] = [d for d in dirs if not _skip_dir(base / d, prefix + d)]
            for name in files:
                rel = prefix + name
                if rel not in wanted and not _preserved(rel):
                    with contextlib.suppress(OSError):
                        (base / name).unlink()
        keep_dirs = {p for rel in wanted for p in _parents(rel)}
        for current, _, _ in os.walk(root, topdown=False, followlinks=False):
            base = Path(current)
            rel = base.relative_to(root).as_posix()
            if rel == "." or _preserved(rel + "/") or rel in keep_dirs:
                continue
            with contextlib.suppress(OSError):
                base.rmdir()


def _skip_dir(full: Path, rel: str) -> bool:
    """Не заходить в каталог: поддерево сборки или ссылка (ссылку вне сборки удаляем)."""
    if full.is_symlink():
        if not _preserved(rel + "/"):
            full.unlink()
        return True
    return _preserved(rel + "/")


def _preserved(rel: str) -> bool:
    return any(rel.startswith(p) for p in PRESERVED_PREFIXES)


def _parents(rel: str) -> list[str]:
    parts = rel.split("/")[:-1]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


def _ensure_real_dir(path: Path) -> None:
    """Каталог должен быть настоящим: ссылку, подложенную сборкой, заменяем каталогом."""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        path.mkdir()
        return
    if stat.S_ISDIR(mode):
        return
    path.unlink()
    path.mkdir()
