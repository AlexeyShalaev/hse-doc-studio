"""Файлы под папкой паков рабочего пространства (порт IPackWorkspaceFiles).

Путь уже прошёл строковую проверку (`core/pack_studio/paths.py`). Здесь проверяется диск: ни одна часть пути под
папкой паков не может быть символьной ссылкой (запись по ссылке ушла бы за пределы пространства), файл открывается
с `O_NOFOLLOW`, запись идёт во временный файл рядом и атомарно заменяет прежний. Обход дерева не идёт по ссылкам и
пропускает служебные папки git.
"""

from __future__ import annotations

import contextlib
import os
import secrets
import shutil
import stat
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import structlog
import yaml

from hse_doc_studio.core.pack_studio.entities import (
    PackTree,
    ReleasedVersions,
    TreeFile,
    TreePack,
    TreeTemplate,
    TreeVersion,
)
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import (
    PACK_MANIFEST,
    RELEASES_FILE,
    TEMPLATE_MANIFEST,
    TEMPLATES_DIR,
    VERSION_MANIFEST,
    VERSIONS_DIR,
    template_key,
)
from hse_doc_studio.core.pack_studio.protection import Protection
from hse_doc_studio.core.pack_studio.protocols import WorkspaceLimits
from hse_doc_studio.core.template_versions import parse_version_key
from hse_doc_studio.infra.template.releases import load_releases, version_digest

logger = structlog.get_logger()

# Служебное git и мусор файловых менеджеров: в дереве Студии шаблонов их нет.
_SKIP_NAMES = frozenset({".git", ".DS_Store", "Thumbs.db", "desktop.ini", "__pycache__"})
_TMP_PREFIX = ".hse-pack-studio-"
# Манифест пака, шаблона или версии больше этого не читается: дерево не должно разбирать мегабайты YAML.
_MANIFEST_MAX_BYTES = 512 * 1024
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _not_allowed() -> PackStudioError:
    return PackStudioError(PackStudioErrorCode.path_not_allowed)


def _not_found(path: str) -> PackStudioError:
    return PackStudioError(PackStudioErrorCode.file_not_found, path=path)


def _walk_checked(root: Path, path: str) -> Path:
    """Полный путь; любая существующая часть под `root` не ссылка, и все, кроме последней, это папки."""
    current = root
    parts = path.split("/")
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return root.joinpath(*parts)
        except OSError:
            raise _not_allowed() from None
        if stat.S_ISLNK(info.st_mode):
            raise _not_allowed()
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise _not_allowed()
    return current


def _root_of(root: Path) -> Path:
    if root.is_symlink():
        raise _not_allowed()
    return root


class LocalPackWorkspaceFiles:
    def read(self, root: Path, path: str, *, max_bytes: int) -> bytes:
        target = _walk_checked(_root_of(root), path)
        try:
            fd = os.open(target, os.O_RDONLY | _NOFOLLOW)
        except FileNotFoundError:
            raise _not_found(path) from None
        except OSError:
            raise _not_allowed() from None
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if stat.S_ISDIR(info.st_mode):
                raise _not_found(path)
            if not stat.S_ISREG(info.st_mode):
                raise _not_allowed()
            if info.st_size > max_bytes:
                raise PackStudioError(PackStudioErrorCode.file_too_large, limit=max_bytes)
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise PackStudioError(PackStudioErrorCode.file_too_large, limit=max_bytes)
        return data

    def write(self, root: Path, path: str, content: bytes) -> None:
        base = _root_of(root)
        target = _walk_checked(base, path)
        if target.is_dir():
            raise _not_allowed()
        self._make_parents(base, path)
        mode = 0o644
        with contextlib.suppress(FileNotFoundError):
            mode = stat.S_IMODE(os.lstat(target).st_mode)
        temp = target.parent / f"{_TMP_PREFIX}{secrets.token_hex(6)}"
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, mode)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

    def delete(self, root: Path, path: str) -> bool:
        target = _walk_checked(_root_of(root), path)
        try:
            info = os.lstat(target)
        except FileNotFoundError:
            raise _not_found(path) from None
        if stat.S_ISDIR(info.st_mode):
            shutil.rmtree(target)
            return True
        target.unlink()
        return False

    def is_dir(self, root: Path, path: str) -> bool:
        target = _walk_checked(_root_of(root), path)
        try:
            return stat.S_ISDIR(os.lstat(target).st_mode)
        except FileNotFoundError:
            return False

    def registries(self, root: Path) -> tuple[str, ...]:
        found: list[str] = []
        for pack in _subdirs(root):
            for template in _subdirs(pack / TEMPLATES_DIR):
                registry = template / RELEASES_FILE
                if registry.is_file() and not registry.is_symlink():
                    found.append(registry.relative_to(root).as_posix())
        return tuple(sorted(found))

    def released_on_disk(self, root: Path) -> ReleasedVersions:
        templates: dict[str, dict[str, str]] = {}
        for registry in self.registries(root):
            pack, _, template, _ = registry.split("/")
            entries = load_releases(root / pack / TEMPLATES_DIR / template)
            templates[template_key(pack, template)] = {v: e.digest for v, e in entries.items()}
        return ReleasedVersions(templates=templates)

    def tree(self, root: Path, protection: Protection, *, max_files: int) -> PackTree:
        if not root.is_dir() or root.is_symlink():
            return PackTree(packs=(), files=())
        packs = tuple(_pack(root, pack_dir, protection.released) for pack_dir in _subdirs(root) if _has_pack(pack_dir))
        files: list[TreeFile] = []
        truncated = False
        for rel, is_dir, size in _walk(root):
            if len(files) >= max_files:
                truncated = True
                break
            reason = protection.read_only_reason(rel)
            files.append(TreeFile(rel, is_dir, size, reason.value if reason is not None else None))
        return PackTree(packs=packs, files=tuple(files), truncated=truncated)

    def check_packs_root(self, root: Path) -> None:
        if not root.exists():
            return
        if root.is_symlink() or not root.is_dir():
            raise PackStudioError(PackStudioErrorCode.not_a_pack_repo)
        entries = [entry for entry in root.iterdir() if entry.name not in _SKIP_NAMES]
        if entries and not any(_has_pack(entry) for entry in entries):
            raise PackStudioError(PackStudioErrorCode.not_a_pack_repo)

    def measure(self, root: Path, limits: WorkspaceLimits) -> None:
        files = 0
        total = 0
        for _, is_dir, size in _walk(root):
            if is_dir:
                continue
            files += 1
            total += size
            if files > limits.max_tree_files or total > limits.max_tree_bytes:
                raise PackStudioError(PackStudioErrorCode.workspace_too_large)

    @staticmethod
    def _make_parents(base: Path, path: str) -> None:
        current = base
        for part in path.split("/")[:-1]:
            current = current / part
            try:
                current.mkdir(exist_ok=True)
            except FileExistsError:
                raise _not_allowed() from None
            if current.is_symlink() or not current.is_dir():
                raise _not_allowed()


def _subdirs(folder: Path) -> list[Path]:
    if not folder.is_dir() or folder.is_symlink():
        return []
    return sorted(
        (
            entry
            for entry in folder.iterdir()
            if entry.is_dir() and not entry.is_symlink() and entry.name not in _SKIP_NAMES
        ),
        key=lambda entry: entry.name,
    )


def _has_pack(folder: Path) -> bool:
    manifest = folder / PACK_MANIFEST
    return folder.is_dir() and not folder.is_symlink() and manifest.is_file() and not manifest.is_symlink()


def _walk(root: Path) -> Iterator[tuple[str, bool, int]]:
    """(путь от `root`, папка ли, размер) в порядке обхода; ссылки и служебные имена пропускаются."""
    for current, dirs, names in os.walk(root, followlinks=False):
        here = Path(current)
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_NAMES and not (here / d).is_symlink())
        for name in dirs:
            yield (here / name).relative_to(root).as_posix(), True, 0
        for name in sorted(names):
            if name in _SKIP_NAMES or name.startswith(_TMP_PREFIX):
                continue
            path = here / name
            try:
                info = os.lstat(path)
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                yield path.relative_to(root).as_posix(), False, info.st_size


def _manifest(path: Path) -> Mapping[str, Any]:
    """Разобранный манифест или пустой словарь: битый пак в дереве виден, но без подписей."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MANIFEST_MAX_BYTES:
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        logger.info("pack studio: manifest is unreadable", path=str(path), exc=str(exc))
        return {}
    return data if isinstance(data, dict) else {}


def _localized(value: object) -> dict[str, str] | None:
    if isinstance(value, str):
        return {"ru": value}
    if isinstance(value, dict):
        found = {str(k): str(v) for k, v in value.items() if isinstance(v, str | int | float)}
        return found or None
    return None


def _text(value: object) -> str | None:
    return str(value) if isinstance(value, str | int | float) and not isinstance(value, bool) else None


def _pack(root: Path, pack_dir: Path, released: ReleasedVersions) -> TreePack:
    data = _manifest(pack_dir / PACK_MANIFEST)
    templates = tuple(
        _template(root, pack_dir.name, template_dir, released) for template_dir in _subdirs(pack_dir / TEMPLATES_DIR)
    )
    return TreePack(
        id=_text(data.get("id")) or pack_dir.name,
        path=pack_dir.relative_to(root).as_posix(),
        name=_localized(data.get("name")),
        templates=templates,
    )


def _version_order(name: str) -> tuple[int, tuple[int, int, int], str]:
    """Номера по возрастанию, затем папки с неразобранным именем по алфавиту."""
    key = parse_version_key(name)
    return (0, key, "") if key is not None else (1, (0, 0, 0), name)


def _template(root: Path, pack: str, template_dir: Path, released: ReleasedVersions) -> TreeTemplate:
    data = _manifest(template_dir / TEMPLATE_MANIFEST)
    versions = sorted(_subdirs(template_dir / VERSIONS_DIR), key=lambda d: _version_order(d.name))
    return TreeTemplate(
        id=_text(data.get("id")) or template_dir.name,
        path=template_dir.relative_to(root).as_posix(),
        name=_localized(data.get("name")),
        default_version=_text(data.get("default_version")),
        versions=tuple(_version(root, pack, template_dir.name, d, released) for d in versions),
    )


def _version(root: Path, pack: str, template: str, version_dir: Path, released: ReleasedVersions) -> TreeVersion:
    data = _manifest(version_dir / VERSION_MANIFEST)
    expected = released.digest(pack, template, version_dir.name)
    modified = False
    if expected is not None:
        try:
            modified = version_digest(version_dir) != expected
        except OSError:
            modified = True
    return TreeVersion(
        version=version_dir.name,
        path=version_dir.relative_to(root).as_posix(),
        status=_text(data.get("status")),
        released=expected is not None,
        modified=modified,
    )
