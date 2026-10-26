"""Нагрузка и результат задачи pack.submission: сборка архива сдачи по готовому плану.

Планировщик на стороне API заранее решает всё, что требует проекта: экземпляры
документов, имена в архиве, штампы, замороженные копии и подписи, тексты форм,
публичные ключи. Исполнителю остаётся применить записи по порядку.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.base import JobPayload, JobResultData
from hse_doc_studio.core.jobs.files import (
    ArtifactRef,
    InlineBlob,
    ManifestFile,
    StampSpec,
    validate_relative_posix,
)


class ArchiveFormat(StrEnum):
    zip = "zip"
    targz = "targz"
    sevenz = "7z"
    rar = "rar"


class PackEntryKind(StrEnum):
    # Скопировать файл как есть.
    copy = "copy"
    # Скопировать PDF, наложив штампы.
    stamp_pdf = "stamp_pdf"
    # Записать готовый текст (UTF-8).
    text = "text"
    # Записать небольшие готовые байты (например, публичный ключ).
    blob = "blob"


@dataclass(frozen=True)
class PackEntry:
    """Одна запись архива. Плоская: поля чужих видов должны быть пустыми."""

    kind: PackEntryKind
    # Путь внутри архива.
    arcname: str
    source: ManifestFile | None = None
    stamps: tuple[StampSpec, ...] = ()
    text: str | None = None
    blob: InlineBlob | None = None
    # Запись, без которой пакет теряет смысл (замороженный PDF и его подписи): сбой записи
    # такой записи роняет сборку, а не пропускает её.
    critical: bool = False

    def __post_init__(self) -> None:
        validate_relative_posix(self.arcname)
        has_source = self.kind in (PackEntryKind.copy, PackEntryKind.stamp_pdf)
        if has_source != (self.source is not None):
            raise ValueError(f"{self.kind} entry {'needs' if has_source else 'must not have'} a source")
        if self.stamps and self.kind is not PackEntryKind.stamp_pdf:
            raise ValueError(f"{self.kind} entry must not have stamps")
        if (self.kind is PackEntryKind.text) != (self.text is not None):
            raise ValueError(
                f"{self.kind} entry {'needs' if self.kind is PackEntryKind.text else 'must not have'} text"
            )
        if (self.kind is PackEntryKind.blob) != (self.blob is not None):
            raise ValueError(
                f"{self.kind} entry {'needs' if self.kind is PackEntryKind.blob else 'must not have'} a blob"
            )

    def manifest_files(self) -> tuple[ManifestFile, ...]:
        """Входные файлы проекта, на которые ссылается запись: исходник и картинки штампов."""
        files = [self.source] if self.source is not None else []
        files.extend(stamp.png for stamp in self.stamps if stamp.png is not None)
        return tuple(files)


@dataclass(frozen=True)
class PackSubmissionPayload(JobPayload):
    # Имя папки и архива без расширения (профиль, слаг, время, суффикс).
    base_name: str
    profile_id: str
    lang: Lang
    archive_format: ArchiveFormat
    # Оставить собранную папку рядом с архивом (локальный режим).
    keep_folder: bool
    entries: tuple[PackEntry, ...]
    # Сверять sha256 входов из манифеста перед сборкой.
    verify_manifest: bool = False

    def __post_init__(self) -> None:
        validate_relative_posix(self.base_name)
        if "/" in self.base_name:
            raise ValueError(f"base_name must be a single path segment: {self.base_name!r}")

    def manifest_files(self) -> tuple[ManifestFile, ...]:
        """Все входные файлы проекта без повторов, в порядке первого упоминания."""
        by_path: dict[str, ManifestFile] = {}
        for entry in self.entries:
            for file in entry.manifest_files():
                known = by_path.setdefault(file.path, file)
                if known != file:
                    raise ValueError(f"manifest lists {file.path!r} with different hash or size")
        return tuple(by_path.values())


@dataclass(frozen=True)
class PackSkip:
    """Запись, которую не удалось положить в архив, и почему."""

    arcname: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class PackResult(JobResultData):
    archive: ArtifactRef
    folder: ArtifactRef | None = None
    # Имена, реально попавшие в архив.
    written: tuple[str, ...] = ()
    skipped: tuple[PackSkip, ...] = ()
