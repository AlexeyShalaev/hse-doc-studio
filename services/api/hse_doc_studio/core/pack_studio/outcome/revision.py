"""Ревизия результата: дайджест текстов манифестов, по которым считали (ключ кэша и признак устаревшего ответа)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

REVISION_PREFIX = "sha256-"
REVISION_LENGTH = 16


def revision_of(manifests: Mapping[str, str | bytes]) -> str:
    """Ревизия по манифестам: путь от каталога версии и текст (`version.yaml`, `files/*/doc.yaml`, файлы примера).

    Порядок путей не важен, правка любого текста меняет ревизию. Читает файлы вызывающий, здесь только хэш."""
    digest = hashlib.sha256()
    for path in sorted(manifests):
        content = manifests[path]
        raw = content.encode("utf-8") if isinstance(content, str) else content
        digest.update(f"{path}\0{hashlib.sha256(raw).hexdigest()}\n".encode())
    return REVISION_PREFIX + digest.hexdigest()[:REVISION_LENGTH]
