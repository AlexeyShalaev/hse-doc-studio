"""Безопасность путей из чужого дерева.

Удалённый репозиторий может прислать путь, который вышел бы из папки проекта или
подменил служебные файлы Студии. Такие пути не записываются никогда: планировщик
пропускает их и предупреждает. Имена сравниваются в NFC без учёта регистра, как их
видят macOS и Windows: `Глава.tex` и `глава.tex` на таких системах один файл.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

_STUDIO_DIR = ".hse-studio"
# Служебные каталоги Студии: их содержимое локально и из чужого дерева не принимается.
_STUDIO_PRIVATE_DIRS = frozenset({"git", "update", "compiles", "chats", "backup", "submissions"})
_REGULAR_FILE_MODES = frozenset({"100644", "100755"})
_GIT_NAMES = frozenset({".git", "git~1"})


def comparison_key(path: str) -> str:
    """Ключ сравнения имён: NFC и свёртка регистра."""
    return unicodedata.normalize("NFC", path).casefold()


def _segment_key(segment: str) -> str:
    # Невидимые символы форматирования и хвостовые точки с пробелами файловые системы игнорируют.
    visible = "".join(ch for ch in segment if unicodedata.category(ch) != "Cf")
    return comparison_key(visible).rstrip(" .")


def is_safe_path(path: str) -> bool:
    """Можно ли записать такой относительный путь внутрь папки проекта."""
    if not path or path.startswith("/") or "\\" in path:
        return False
    if any(unicodedata.category(ch) == "Cc" for ch in path):
        return False
    segments = path.split("/")
    keys = [_segment_key(segment) for segment in segments]
    # Пустой ключ: «», «.», «..», «...» и всё, что Windows сводит к ним.
    if any(not key or ":" in segment for key, segment in zip(keys, segments, strict=True)):
        return False
    if any(key in _GIT_NAMES for key in keys):
        return False
    return not (len(keys) > 1 and keys[0] == _STUDIO_DIR and keys[1] in _STUDIO_PRIVATE_DIRS)


def is_safe_entry(path: str, mode: str) -> bool:
    """Путь безопасен, и запись дерева — обычный файл (не символьная ссылка и не подмодуль)."""
    return mode in _REGULAR_FILE_MODES and is_safe_path(path)


def collision_groups(paths: Iterable[str]) -> list[tuple[str, ...]]:
    """Группы разных имён, совпадающих в NFC без учёта регистра; внутри группы имена по порядку."""
    groups: dict[str, set[str]] = {}
    for path in paths:
        groups.setdefault(comparison_key(path), set()).add(path)
    return [tuple(sorted(names)) for key, names in sorted(groups.items()) if len(names) > 1]
