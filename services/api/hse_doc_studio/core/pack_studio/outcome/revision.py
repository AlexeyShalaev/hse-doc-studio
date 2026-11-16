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


VERSION_MANIFEST = "version.yaml"
EXAMPLES_DIR = "examples"
_EXAMPLE_SUFFIXES = (".yaml", ".yml")


def is_manifest_path(path: str) -> bool:
    """Манифест версии по пути от каталога версии: `version.yaml` и `files/<документ>/doc.yaml`."""
    parts = path.split("/")
    return path == VERSION_MANIFEST or (len(parts) == 3 and parts[0] == "files" and parts[2] == "doc.yaml")  # noqa: PLR2004


def example_file_names(example_id: str) -> tuple[str, ...]:
    """Имена файла набора данных от каталога шаблона; у автонабора (`auto:*`) файла нет."""
    if not example_id or example_id.startswith("auto:") or "/" in example_id:
        return ()
    return tuple(f"{EXAMPLES_DIR}/{example_id}{suffix}" for suffix in _EXAMPLE_SUFFIXES)
