"""Единственные формы файлов и блобов для всех семейств задач."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Потолок встроенного блоба. Применяет только невстроенный диспетчер; встроенный
# его не проверяет, чтобы не менять поведение локального режима.
MAX_INLINE_BYTES = 8 * 1024 * 1024


def validate_relative_posix(path: str) -> None:
    if not path:
        raise ValueError("path is empty")
    if "\\" in path:
        raise ValueError(f"path has a backslash: {path!r}")
    if path.startswith("/"):
        raise ValueError(f"path is absolute: {path!r}")
    if ".." in path.split("/"):
        raise ValueError(f"path escapes the root: {path!r}")


@dataclass(frozen=True)
class ManifestFile:
    """Файл проекта: путь от корня в POSIX-форме, при желании с хешем и размером."""

    path: str
    sha256: str | None = None
    size: int | None = None

    def __post_init__(self) -> None:
        validate_relative_posix(self.path)


@dataclass(frozen=True)
class InlineBlob:
    """Небольшие данные, едущие внутри нагрузки (подпись, цепочка, публичный ключ)."""

    data_b64: str

    @classmethod
    def from_bytes(cls, data: bytes) -> InlineBlob:
        return cls(data_b64=base64.b64encode(data).decode("ascii"))

    def to_bytes(self) -> bytes:
        return base64.b64decode(self.data_b64.encode("ascii"))


@dataclass(frozen=True)
class ArtifactRef:
    """Единственная форма выхода задачи: файл относительно рабочей папки."""

    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        validate_relative_posix(self.path)


@dataclass(frozen=True)
class StampSpec:
    """Проводная копия `Stamp` поле в поле; вместо `png_path` стоит `png`."""

    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    png: ManifestFile | None
    aspect_ratio: float
    text: str | None = None
    details: tuple[tuple[str, str], ...] = ()
    subtitle: str = ""
    date_label: str = ""
    date_text: str | None = None


class IProjectFileProbe(Protocol):
    """Чтение проекта по относительным путям, чтобы планировщик не знал про диск."""

    def is_file(self, path: str) -> bool: ...
    def size(self, path: str) -> int: ...
    def sha256(self, path: str) -> str: ...
    def read_text(self, path: str) -> str: ...
    def read_bytes(self, path: str) -> bytes: ...
    def list_files(self, prefix: str = "") -> tuple[str, ...]: ...


class IProjectFileProbeFactory(Protocol):
    """Привязывает чтение к корню проекта: сам зонд корня не знает, пути у него относительные."""

    def for_root(self, root: Path) -> IProjectFileProbe: ...
