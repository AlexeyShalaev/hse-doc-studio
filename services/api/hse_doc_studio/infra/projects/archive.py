"""Приём zip-архива проекта из локальной Студии: проверка целиком, затем распаковка через `safe_open`.

Что отвергает `inspect`: путь наружу (`..`, абсолютный, с диском или обратным слэшем), симлинк и любой
необычный файл, шифрование, повторные имена, лишние файлы и распухший размер. Распаковка не доверяет
заявленным размерам: байты считаются при чтении, превышение обрывает приём.
"""

from __future__ import annotations

import json
import re
import stat
import unicodedata
import zipfile
import zlib
from pathlib import Path
from typing import Any
from uuid import UUID

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.project_schema import can_write
from hse_doc_studio.core.projects.importer import (
    ArchiveManifest,
    ExtractedProject,
    ImportLimits,
    ProjectImportCode,
    ProjectImportError,
)
from hse_doc_studio.core.projects.volume import IProjectVolume, UnsafePathError
from hse_doc_studio.infra.git_sync.store_hardening import GitStoreGuard
from hse_doc_studio.infra.persistence.project_migrations import needs_migration
from hse_doc_studio.infra.persistence.serializers import deserialize_project, deserialize_project_schema

_STUDIO = ".hse-studio"
_PROJECT_JSON = f"{_STUDIO}/project.json"
_JUNK_DIRS = frozenset({"__MACOSX"})
_JUNK_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})
# Записи с путями на диске автора: на сервере они бесполезны, документ собирается заново.
_RECORD_PREFIXES = (f"{_STUDIO}/compiles/", f"{_STUDIO}/submissions/")
_HOOKS_PREFIX = f"{_STUDIO}/git/hooks/"
_PROJECT_JSON_MAX = 5 * 1024 * 1024
_CHUNK = 1024 * 1024
_DRIVE = re.compile(r"^[A-Za-z]:")
_REGULAR_OR_DIR = (stat.S_IFREG, stat.S_IFDIR)


def _refuse(code: ProjectImportCode, ru: str, en: str) -> ProjectImportError:
    return ProjectImportError(code, localized_error(ru, en))


def _unsafe(name: str) -> ProjectImportError:
    shown = name[:120]
    return _refuse(
        ProjectImportCode.archive_unsafe,
        f"Архив отклонён: недопустимый путь или тип файла ({shown!r}).",
        f"The archive was rejected: unsafe path or file type ({shown!r}).",
    )


def _clean_name(info: zipfile.ZipInfo) -> str:
    """Путь внутри архива без хвостового слэша каталога; небезопасное имя отвергает весь архив."""
    name = info.filename
    if not name or "\x00" in name or "\\" in name or name.startswith("/") or _DRIVE.match(name):
        raise _unsafe(name)
    trimmed = name.rstrip("/") if info.is_dir() else name
    parts = trimmed.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise _unsafe(name)
    return trimmed


def _check_type(info: zipfile.ZipInfo) -> None:
    if info.flag_bits & 0x1:
        raise _refuse(
            ProjectImportCode.archive_unsafe,
            "Архив зашифрован: снимите пароль и загрузите его снова.",
            "The archive is encrypted: remove the password and upload it again.",
        )
    kind = stat.S_IFMT((info.external_attr >> 16) & 0xFFFF)
    if kind and kind not in _REGULAR_OR_DIR:
        raise _unsafe(info.filename)


def _is_junk(rel: str) -> bool:
    parts = rel.split("/")
    return parts[0] in _JUNK_DIRS or parts[-1] in _JUNK_FILES


def _find_prefix(names: list[str]) -> str:
    """Каталог, в котором лежит `.hse-studio/project.json`: корень архива или единственная верхняя папка."""
    live = [n for n in names if not _is_junk(n)]
    if _PROJECT_JSON in live:
        return ""
    tops = {n.split("/", 1)[0] for n in live if "/" in n}
    bare = [n for n in live if "/" not in n]
    if len(tops) == 1 and not bare:
        top = next(iter(tops))
        if f"{top}/{_PROJECT_JSON}" in live:
            return f"{top}/"
    raise _refuse(
        ProjectImportCode.no_project,
        "В архиве нет проекта Студии: не найден .hse-studio/project.json. Заархивируйте папку проекта целиком, "
        "вместе со скрытой папкой .hse-studio.",
        "The archive holds no Studio project: .hse-studio/project.json is missing. Zip the whole project folder, "
        "including the hidden .hse-studio folder.",
    )


def _read_project(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict[str, Any]:
    if info.file_size > _PROJECT_JSON_MAX:
        raise _refuse(
            ProjectImportCode.archive_invalid,
            "project.json слишком большой.",
            "project.json is too large.",
        )
    try:
        with zf.open(info) as handle:
            data = json.loads(handle.read(_PROJECT_JSON_MAX + 1).decode("utf-8"))
        if not isinstance(data, dict):
            raise TypeError("не объект")
        UUID(str(data["id"]))
        str(data["name"])
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile) as exc:
        raise _refuse(
            ProjectImportCode.no_project,
            "project.json в архиве не читается.",
            "project.json in the archive cannot be read.",
        ) from exc
    return data


def _check_shape(data: dict[str, Any]) -> None:
    schema = deserialize_project_schema(data.get("schema"))
    if not can_write(schema):
        written_by = schema.written_by or "?"
        raise _refuse(
            ProjectImportCode.project_newer,
            f"Проект записан более новой версией Студии ({written_by}): обновите сервер и загрузите его снова.",
            f"The project was saved by a newer Studio ({written_by}): update the server and upload it again.",
        )
    if needs_migration(data):
        # Старую схему доведёт до текущей чтение после распаковки.
        return
    try:
        deserialize_project(data, folder=Path("/"))
    except (KeyError, ValueError, TypeError) as exc:
        raise _refuse(
            ProjectImportCode.no_project,
            "project.json в архиве не читается.",
            "project.json in the archive cannot be read.",
        ) from exc


class ZipProjectArchive:
    def inspect(self, archive: Path, limits: ImportLimits) -> ArchiveManifest:
        try:
            with zipfile.ZipFile(archive) as zf:
                return self._inspect(zf, limits)
        except zipfile.BadZipFile as exc:
            raise _refuse(
                ProjectImportCode.archive_invalid,
                "Это не zip-архив или он повреждён.",
                "This is not a zip archive or it is damaged.",
            ) from exc

    def _inspect(self, zf: zipfile.ZipFile, limits: ImportLimits) -> ArchiveManifest:
        infos = zf.infolist()
        if len(infos) > limits.max_files:
            raise self._too_large(limits)
        names: dict[str, zipfile.ZipInfo] = {}
        seen: set[str] = set()
        total = 0
        for info in infos:
            _check_type(info)
            name = _clean_name(info)
            folded = unicodedata.normalize("NFC", name).casefold()
            if folded in seen:
                raise _unsafe(info.filename)
            seen.add(folded)
            names[name] = info
            if not info.is_dir():
                total += info.file_size
                if total > limits.max_unpacked_bytes:
                    raise self._too_large(limits)
        prefix = _find_prefix([n for n, i in names.items() if not i.is_dir()])
        data = _read_project(zf, names[f"{prefix}{_PROJECT_JSON}"])
        _check_shape(data)
        files = [n[len(prefix) :] for n, i in names.items() if not i.is_dir() and n.startswith(prefix)]
        kept = [f for f in files if not _is_junk(f)]
        config = names.get(f"{prefix}{_STUDIO}/git/config")
        return ArchiveManifest(
            project_id=UUID(str(data["id"])),
            name=str(data["name"]),
            has_remote=config is not None and self._has_remote(zf, config),
            files=sum(1 for f in kept if not f.startswith(_RECORD_PREFIXES) and not f.startswith(_HOOKS_PREFIX)),
            unpacked_bytes=total,
            junk=len(files) - len(kept),
            records=sum(1 for f in kept if f.startswith(_RECORD_PREFIXES)),
            prefix=prefix,
        )

    @staticmethod
    def _has_remote(zf: zipfile.ZipFile, config: zipfile.ZipInfo) -> bool:
        if config.file_size > _PROJECT_JSON_MAX:
            return False
        with zf.open(config) as handle:
            return b"[remote " in handle.read(_PROJECT_JSON_MAX)

    @staticmethod
    def _too_large(limits: ImportLimits) -> ProjectImportError:
        mib = limits.max_unpacked_bytes // (1024 * 1024)
        return _refuse(
            ProjectImportCode.too_large,
            f"Проект больше допустимого: не более {mib} МБ после распаковки и {limits.max_files} файлов.",
            f"The project is too large: at most {mib} MB unpacked and {limits.max_files} files.",
        )

    def extract(
        self, archive: Path, manifest: ArchiveManifest, volume: IProjectVolume, folder: Path
    ) -> ExtractedProject:
        limits_bytes = manifest.unpacked_bytes
        written = 0
        count = 0
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                if info.is_dir() or not info.filename.startswith(manifest.prefix):
                    continue
                rel = info.filename[len(manifest.prefix) :]
                if _is_junk(rel) or rel.startswith((*_RECORD_PREFIXES, _HOOKS_PREFIX)):
                    continue
                written += self._copy(zf, info, volume, folder, rel, limits_bytes - written)
                count += 1
        return ExtractedProject(files=count, bytes=written)

    @staticmethod
    def _copy(
        zf: zipfile.ZipFile, info: zipfile.ZipInfo, volume: IProjectVolume, folder: Path, rel: str, budget: int
    ) -> int:
        size = 0
        try:
            with zf.open(info) as src, volume.safe_open(folder, rel, "wb", make_parents=True) as dst:
                while chunk := src.read(_CHUNK):
                    size += len(chunk)
                    if size > info.file_size or size > budget:
                        raise _refuse(
                            ProjectImportCode.archive_invalid,
                            "Размер файла в архиве не совпадает с заявленным.",
                            "A file size in the archive does not match the declared one.",
                        )
                    dst.write(chunk)
        except UnsafePathError as exc:
            raise _unsafe(rel) from exc
        except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
            raise _refuse(
                ProjectImportCode.archive_invalid,
                "Архив повреждён.",
                "The archive is damaged.",
            ) from exc
        return size

    def harden_store(self, folder: Path) -> int:
        return len(GitStoreGuard().harden(folder))
