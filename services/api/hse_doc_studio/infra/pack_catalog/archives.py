"""Загруженные архивы источников каталога (порт IArchiveStore): `packs-store/.archives/<sha256>.<расширение>`.

Архив принимается потоком во временный файл `.uploads/` рядом (тот же том, предел размера считает роутер), потом
переносится под имя по своему хешу. Одинаковые архивы ложатся в один файл. Проверка содержимого (ссылки, `..`,
число файлов) идёт при раскладке ревизии (`stage.py`), здесь только формат по сигнатуре.
"""

from __future__ import annotations

import hashlib
import os
import re
import tarfile
import uuid
import zipfile
from pathlib import Path

from hse_doc_studio.core.pack_catalog.errors import CatalogError, CatalogErrorCode

ARCHIVES_DIR = ".archives"
_UPLOADS_DIR = ".uploads"
_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 1 << 20


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def archive_suffix(path: Path) -> str | None:
    """`zip` или `tar` по содержимому (сжатие tar любое, его понимает `tarfile`); None: ни то, ни другое."""
    if zipfile.is_zipfile(path):
        return "zip"
    try:
        return "tar" if tarfile.is_tarfile(path) else None
    except OSError:
        return None


class FsArchiveStore:
    def __init__(self, root: Path) -> None:
        self._dir = root / ARCHIVES_DIR
        self._uploads = root / _UPLOADS_DIR

    def upload_path(self) -> Path:
        self._uploads.mkdir(parents=True, exist_ok=True)
        return self._uploads / f"{uuid.uuid4().hex}.part"

    def save(self, upload: Path, *, name: str) -> str:
        try:
            suffix = archive_suffix(upload)
            if suffix is None:
                raise CatalogError(CatalogErrorCode.archive_invalid, name=name[:200])
            digest = _sha256(upload)
            self._dir.mkdir(parents=True, exist_ok=True)
            target = self._dir / f"{digest}.{suffix}"
            if target.is_file():
                return digest
            os.replace(upload, target)
            return digest
        finally:
            upload.unlink(missing_ok=True)

    def path(self, digest: str) -> Path | None:
        if not _HEX_RE.fullmatch(digest):
            return None
        for suffix in ("zip", "tar"):
            candidate = self._dir / f"{digest}.{suffix}"
            if candidate.is_file() and not candidate.is_symlink():
                return candidate
        return None
