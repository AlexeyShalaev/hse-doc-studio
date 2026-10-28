"""Сборщик выходов задачи в рабочей папке раннера.

Сборка исполняет пользовательский код и может положить в папку что угодно, в том числе ссылки
на файлы хоста. Поэтому берутся только обычные файлы без ссылок, из белого списка шаблонов,
открытые без перехода по ссылке; неизменившиеся файлы манифеста пропускаются.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import stat
from collections.abc import Collection, Mapping
from pathlib import Path

from hse_doc_studio.core.jobs.files import ArtifactRef, validate_relative_posix
from hse_doc_studio.infra.runner.executor import OutputFile

_CHUNK = 1024 * 1024


def collect_outputs(
    root: Path,
    patterns: Collection[str],
    baseline: Mapping[str, str] | None = None,
    *,
    max_file_bytes: int | None = None,
) -> tuple[OutputFile, ...]:
    """Выходы под шаблонами `fnmatch` по POSIX-пути от корня (`*` пересекает `/`).

    Пропускаются ссылки, не обычные файлы, файлы с несколькими жёсткими ссылками, слишком большие
    и совпадающие по хешу с `baseline`.
    """
    base = baseline or {}
    found: list[OutputFile] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        here = Path(current)
        prefix = here.relative_to(root).as_posix()
        for name in sorted(files):
            rel = name if prefix == "." else f"{prefix}/{name}"
            if not any(fnmatch.fnmatchcase(rel, p) for p in patterns):
                continue
            try:
                validate_relative_posix(rel)
            except ValueError:
                continue
            described = _describe(here / name, rel, max_file_bytes)
            if described is None or base.get(rel) == described.sha256:
                continue
            found.append(OutputFile(ref=described, path=here / name))
    return tuple(found)


def _describe(path: Path, rel: str, max_file_bytes: int | None) -> ArtifactRef | None:
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
            return None
        if max_file_bytes is not None and info.st_size > max_file_bytes:
            return None
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(fd, "rb", closefd=False) as handle:
            for chunk in iter(lambda: handle.read(_CHUNK), b""):
                digest.update(chunk)
                size += len(chunk)
    finally:
        os.close(fd)
    return ArtifactRef(path=rel, sha256=digest.hexdigest(), size=size)
