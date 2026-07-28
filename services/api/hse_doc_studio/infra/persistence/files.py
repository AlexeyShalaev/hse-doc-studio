from __future__ import annotations

import os
import shutil
from pathlib import Path

import structlog

from hse_doc_studio.core.repositories import ScannedEntry

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"
# Каталоги, внутрь которых обход не спускается вовсе. `.hse-studio` — наше
# служебное хранилище (git версий, записи сборок, чаты), `.build` — промежуточные
# файлы latexmk, которые пересоздаются на каждой сборке. Ни то, ни другое не
# является документами пользователя: в дереве «Файлы проекта» им не место, а
# обход из-за них разрастался вчетверо.
_SKIP_DIRS = frozenset({_HSE_STUDIO, ".build", ".git"})


class LocalFileRepository:
    """Reads/writes project files, with path traversal protection."""

    def _safe_path(self, folder: Path, path: str) -> Path:
        target = (folder / path).resolve()
        if not target.is_relative_to(folder.resolve()):
            raise PermissionError(f"Path traversal detected: '{path}' escapes project folder '{folder}'")
        return target

    def _safe_mutable_path(self, folder: Path, path: str) -> Path:
        """Like `_safe_path`, but additionally forbids destructive operations on
        the project root itself and on the internal `.hse-studio` directory
        (git history, agent state) — these must never be touched via the file API."""
        target = self._safe_path(folder, path)
        resolved = target.resolve()
        folder_resolved = folder.resolve()
        if resolved == folder_resolved:
            raise PermissionError("Refusing to modify the project root")
        studio = (folder / _HSE_STUDIO).resolve()
        if resolved == studio or studio in resolved.parents:
            raise PermissionError(f"Refusing to modify internal path: '{path}'")
        return target

    def read(self, folder: Path, path: str) -> bytes:
        target = self._safe_path(folder, path)
        return target.read_bytes()

    def write(self, folder: Path, path: str, content: bytes) -> None:
        target = self._safe_path(folder, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        logger.debug("file written", folder=str(folder), path=path)

    def scan(self, folder: Path) -> list[ScannedEntry]:
        """Один обход дерева проекта: файлы и папки вместе, состатистикой.

        Раньше дерево строилось ТРЕМЯ проходами — `rglob` за файлами, второй
        `rglob` за папками и `stat()` на каждый элемент в use case, — плюс
        `Path.resolve()` на каждую запись ради проверки «не внутри ли
        .hse-studio». На бинд-маунте Docker каждый такой системный вызов стоит
        дорого: командный ВКР отдавал дерево ~24 секунды.

        Теперь один `os.walk` с ОТСЕЧЕНИЕМ служебных каталогов на входе (в них
        просто не спускаемся) и `os.DirEntry.stat()`, который переиспользует
        данные, уже прочитанные при листинге каталога.
        """
        if not folder.exists():
            return []
        entries: list[ScannedEntry] = []
        root = str(folder)
        for dirpath, dirnames, _filenames in os.walk(root):
            # Мутируем dirnames на месте — так os.walk НЕ спустится внутрь.
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for entry in os.scandir(dirpath):
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                    if is_dir and entry.name in _SKIP_DIRS:
                        continue
                    stat = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    logger.warning("could not stat entry", path=entry.path, exc=str(exc))
                    continue
                rel = os.path.relpath(entry.path, root).replace(os.sep, "/")
                entries.append(ScannedEntry(path=rel, is_dir=is_dir, size=stat.st_size, mtime=stat.st_mtime))
        entries.sort(key=lambda e: e.path)
        return entries

    def list_files(self, folder: Path) -> list[str]:
        return [e.path for e in self.scan(folder) if not e.is_dir]

    def list_dirs(self, folder: Path) -> list[str]:
        """All sub-directories (recursive), excluding the internal `.hse-studio`.
        Lets the UI show empty folders (which carry no files) as first-class nodes."""
        return [e.path for e in self.scan(folder) if e.is_dir]

    def exists(self, folder: Path, path: str) -> bool:
        return self._safe_path(folder, path).exists()

    def delete(self, folder: Path, path: str) -> None:
        target = self._safe_mutable_path(folder, path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: '{path}'")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        logger.debug("file deleted", folder=str(folder), path=path)

    def move(self, folder: Path, src: str, dst: str) -> None:
        source = self._safe_mutable_path(folder, src)
        target = self._safe_mutable_path(folder, dst)
        if not source.exists():
            raise FileNotFoundError(f"Source not found: '{src}'")
        if target.exists():
            raise FileExistsError(f"Destination already exists: '{dst}'")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        logger.debug("file moved", folder=str(folder), src=src, dst=dst)

    def mkdir(self, folder: Path, path: str) -> None:
        target = self._safe_mutable_path(folder, path)
        if target.exists():
            raise FileExistsError(f"Path already exists: '{path}'")
        target.mkdir(parents=True)
        logger.debug("dir created", folder=str(folder), path=path)
