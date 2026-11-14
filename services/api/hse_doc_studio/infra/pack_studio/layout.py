"""Раскладка паков на диске: что лежит под каталогом, который передали CLI (template-studio.md, 11).

Пак это каталог с `pack.yaml`, шаблон это `templates/<шаблон>/` с `template.yaml` и `versions/`, версия это
`versions/<номер>/` с `version.yaml`. Каталог для команды может быть любым из них или папкой с паками.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.template_versions import VersionKey, parse_version_key

PACK_MANIFEST = "pack.yaml"
TEMPLATE_MANIFEST = "template.yaml"
VERSION_MANIFEST = "version.yaml"
VERSIONS_DIR = "versions"
# Служебные каталоги, в которых паков не бывает: обход их пропускает.
_SKIP_DIRS = frozenset({"node_modules", "__pycache__"})


class PackPathError(ValueError):
    """Каталог не найден, не тот вид или в нём нет ни одного пака, шаблона и версии."""


@dataclass(frozen=True)
class PackTree:
    """Что нашлось под каталогами команды; каждый список отсортирован и без повторов."""

    packs: tuple[Path, ...]
    templates: tuple[Path, ...]
    versions: tuple[Path, ...]

    @property
    def empty(self) -> bool:
        return not (self.packs or self.templates or self.versions)


def is_version_dir(path: Path) -> bool:
    return (path / VERSION_MANIFEST).is_file()


def is_template_dir(path: Path) -> bool:
    return (path / VERSIONS_DIR).is_dir() or (path / TEMPLATE_MANIFEST).is_file()


def template_of(version_dir: Path) -> Path | None:
    """Каталог шаблона версии; None, если версия лежит не в `versions/`."""
    return version_dir.parent.parent if version_dir.parent.name == VERSIONS_DIR else None


def _walk(root: Path, name: str) -> Iterable[Path]:
    for path in root.rglob(name):
        parts = path.relative_to(root).parts[:-1]
        if any(part.startswith(".") or part in _SKIP_DIRS for part in parts):
            continue
        if path.is_file():
            yield path


def discover(paths: Iterable[Path]) -> PackTree:
    """Паки, шаблоны и версии под каталогами. Каталог версии даёт только её саму, каталог шаблона его версии."""
    packs: set[Path] = set()
    templates: set[Path] = set()
    versions: set[Path] = set()
    for path in paths:
        if not path.is_dir():
            raise PackPathError(f"{path}: каталог не найден")
        if is_version_dir(path):
            versions.add(path)
            continue
        for manifest in _walk(path, VERSION_MANIFEST):
            if manifest.parent.parent.name == VERSIONS_DIR:
                versions.add(manifest.parent)
                templates.add(manifest.parent.parent.parent)
        templates.update(manifest.parent for manifest in _walk(path, TEMPLATE_MANIFEST))
        packs.update(manifest.parent for manifest in _walk(path, PACK_MANIFEST))
    tree = PackTree(tuple(sorted(packs)), tuple(sorted(templates)), tuple(sorted(versions)))
    if tree.empty:
        raise PackPathError("не найдено ни одного пака, шаблона или версии: " + ", ".join(map(str, paths)))
    return tree


def template_versions(template_dir: Path) -> dict[str, VersionKey]:
    """Версии шаблона с разобранным номером, по возрастанию номера; каталоги с неразборным номером пропускаются."""
    root = template_dir / VERSIONS_DIR
    found = {
        child.name: key
        for child in (root.iterdir() if root.is_dir() else ())
        if is_version_dir(child) and (key := parse_version_key(child.name)) is not None
    }
    return dict(sorted(found.items(), key=lambda item: item[1]))


def require_template(path: Path) -> Path:
    if not path.is_dir() or not (path / VERSIONS_DIR).is_dir():
        raise PackPathError(f"{path}: не каталог шаблона (нужен каталог с versions/)")
    return path


def resolve_version(template_dir: Path, ref: str) -> Path:
    """Каталог версии по номеру (`2026.1.3`) или по пути к каталогу."""
    candidate = template_dir / VERSIONS_DIR / ref
    if is_version_dir(candidate):
        return candidate
    as_path = Path(ref)
    if is_version_dir(as_path):
        return as_path
    raise PackPathError(f"{template_dir.name}: версии {ref} нет (нет {candidate / VERSION_MANIFEST})")
