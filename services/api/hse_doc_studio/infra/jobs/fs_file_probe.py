"""Чтение файлов проекта на локальном диске по относительным путям."""

from __future__ import annotations

import hashlib
from pathlib import Path

from hse_doc_studio.core.jobs.files import IProjectFileProbe, validate_relative_posix


class FsProjectFileProbe:
    """Зонд, привязанный к корню проекта; пути с `..`, обратным слэшем и абсолютные отвергает."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def is_file(self, path: str) -> bool:
        target = self._contained(path)
        return target is not None and target.is_file()

    def size(self, path: str) -> int:
        return self._existing(path).stat().st_size

    def sha256(self, path: str) -> str:
        digest = hashlib.sha256()
        with self._existing(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def read_text(self, path: str) -> str:
        return self._existing(path).read_text(encoding="utf-8")

    def read_bytes(self, path: str) -> bytes:
        return self._existing(path).read_bytes()

    def list_files(self, prefix: str = "") -> tuple[str, ...]:
        base = self._root if not prefix else self._contained(prefix)
        if base is None or not base.is_dir():
            return ()
        return tuple(
            sorted(
                p.relative_to(self._root).as_posix() for p in base.rglob("*") if p.is_file() and self._inside_root(p)
            )
        )

    def _inside_root(self, target: Path) -> bool:
        """Цель внутри корня после раскрытия символьных ссылок: ссылка наружу файлом проекта не считается."""
        try:
            return target.resolve().is_relative_to(self._root.resolve())
        except (OSError, ValueError):
            return False

    def _contained(self, path: str) -> Path | None:
        try:
            validate_relative_posix(path)
        except ValueError:
            return None
        target = self._root / path
        return target if self._inside_root(target) else None

    def _existing(self, path: str) -> Path:
        target = self._contained(path)
        if target is None:
            raise ValueError(f"path is not a project-relative path: {path!r}")
        return target


class FsProjectFileProbeFactory:
    """Stateless: для каждого проекта выдает зонд на его папку."""

    def for_root(self, root: Path) -> IProjectFileProbe:
        return FsProjectFileProbe(root)
