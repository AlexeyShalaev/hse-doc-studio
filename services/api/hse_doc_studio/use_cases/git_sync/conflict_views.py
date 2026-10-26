"""Что экран конфликтов получает от сценариев: сессия, файлы, подробности файла, дифф и содержимое стороны."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from hse_doc_studio.core.git_sync.entities import SyncWarning
from hse_doc_studio.core.git_sync.merge.choices import FileResolution


@dataclass(frozen=True)
class SessionSide:
    """Одна из трёх вершин слияния: коммит и кто его сделал."""

    commit: str
    author: str | None
    at: datetime | None
    message: str | None


@dataclass(frozen=True)
class FileSide:
    """Файл у одной из сторон."""

    exists: bool
    size: int | None = None
    author: str | None = None
    at: datetime | None = None


@dataclass(frozen=True)
class FileSides:
    ours: FileSide
    theirs: FileSide
    base: FileSide


@dataclass(frozen=True)
class ConflictFileView:
    path: str
    owner: str | None
    kind: str
    action: str
    conflict_type: str | None
    hunks: int
    open_hunks: int
    fields: int
    open_fields: int
    resolved: bool
    resolution: FileResolution | None
    allowed: tuple[str, ...]
    default_resolution: str | None
    sides: FileSides
    copy_path: str | None
    doc_id: str | None


@dataclass(frozen=True)
class SessionCounts:
    conflict: int
    auto: int
    total: int


@dataclass(frozen=True)
class ConflictSessionView:
    id: str
    fingerprint: str
    ours: SessionSide
    theirs: SessionSide
    base: SessionSide | None
    counts: SessionCounts
    unresolved: int
    drafts_saved_at: datetime | None
    warnings: tuple[SyncWarning, ...]
    files: tuple[ConflictFileView, ...]


@dataclass(frozen=True)
class TextClean:
    lines: tuple[str, ...]


@dataclass(frozen=True)
class TextHunkView:
    key: str
    ours: tuple[str, ...]
    base: tuple[str, ...]
    theirs: tuple[str, ...]
    ours_start: int
    result_start: int


@dataclass(frozen=True)
class TextDetail:
    eol: str
    truncated: bool
    segments: tuple[TextClean | TextHunkView, ...]


@dataclass(frozen=True)
class JsonFieldView:
    pointer: str
    label: str | None
    type: str
    base: Any
    ours: Any
    theirs: Any
    allowed: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class JsonDetail:
    fields: tuple[JsonFieldView, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BinaryDetail:
    ours: FileSide
    theirs: FileSide
    newer: str
    copy_path: str | None


@dataclass(frozen=True)
class DeleteDetail:
    deleted_by: str


ConflictFileDetail = TextDetail | JsonDetail | BinaryDetail | DeleteDetail


@dataclass(frozen=True)
class ConflictDiff:
    path: str
    binary: bool
    patch: str
    truncated: bool


@dataclass(frozen=True)
class ConflictBlob:
    content: bytes
    media_type: str
    filename: str
