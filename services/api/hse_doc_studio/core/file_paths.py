"""Какие пути файлов пользователь может писать через файловый API проекта.

Запись идёт от интерфейса (сохранение, загрузка с компьютера), агента и MCP. Все они пишут файлы
работы пользователя, а не служебное состояние: `.hse-studio/` держит project.json, подписи и
историю, `.git/` чужой репозиторий с хуками, `.build/` промежуточные файлы сборки. Запись туда
обходила бы права и проверки самих этих данных, поэтому такие пути отклоняются целиком.
"""

from __future__ import annotations

from enum import StrEnum

from hse_doc_studio.core.i18n import localized_error

INVALID_FILE_PATH = "invalid_file_path"

# Служебные папки проекта: в любом месте пути, без учёта регистра (файловые системы macOS и Windows
# не различают `.GIT` и `.git`).
RESERVED_SEGMENTS = frozenset({".hse-studio", ".git", ".build"})
# Предел имени одного файла или папки в байтах UTF-8: больше не примут ext4 и APFS.
MAX_SEGMENT_BYTES = 255
MAX_PATH_BYTES = 1024


class FilePathProblem(StrEnum):
    empty = "empty"
    absolute = "absolute"
    parent = "parent"
    bad_char = "bad_char"
    reserved = "reserved"
    too_long = "too_long"


_MESSAGES: dict[FilePathProblem, tuple[str, str]] = {
    FilePathProblem.empty: ("Пустой путь файла.", "The file path is empty."),
    FilePathProblem.absolute: (
        "Путь файла должен быть внутри проекта, без ведущего «/».",
        "The file path must be inside the project, without a leading '/'.",
    ),
    FilePathProblem.parent: (
        "Путь файла не может выходить из проекта через «..».",
        "The file path cannot leave the project with '..'.",
    ),
    FilePathProblem.bad_char: (
        "В имени файла есть недопустимые символы: обратная косая черта или управляющие символы.",
        "The file name has forbidden characters: a backslash or control characters.",
    ),
    FilePathProblem.reserved: (
        "Служебные папки проекта (.hse-studio, .git, .build) через файлы менять нельзя.",
        "Service folders of the project (.hse-studio, .git, .build) cannot be changed as files.",
    ),
    FilePathProblem.too_long: ("Слишком длинное имя файла.", "The file name is too long."),
}


class InvalidFilePathError(ValueError):
    """Путь нельзя записать через файловый API; роутер отвечает 400 с кодом invalid_file_path."""

    def __init__(self, path: str, problem: FilePathProblem) -> None:
        super().__init__(f"invalid file path {path!r}: {problem.value}")
        self.path = path
        self.problem = problem

    def message(self) -> str:
        ru, en = _MESSAGES[self.problem]
        return localized_error(ru, en)


def _segment_problem(segment: str) -> FilePathProblem | None:
    if segment == "..":
        return FilePathProblem.parent
    if "\\" in segment or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in segment):  # noqa: PLR2004
        return FilePathProblem.bad_char
    if segment.casefold() in RESERVED_SEGMENTS:
        return FilePathProblem.reserved
    if len(segment.encode("utf-8")) > MAX_SEGMENT_BYTES:
        return FilePathProblem.too_long
    return None


def writable_file_path(path: str) -> str:
    """Нормализованный POSIX-путь файла от корня проекта или InvalidFilePathError.

    Пустые сегменты и `.` убираются; `..`, ведущий `/`, обратная косая черта, управляющие символы,
    служебные папки и слишком длинные имена отклоняются.
    """
    if path.startswith("/") and path.strip("/"):
        raise InvalidFilePathError(path, FilePathProblem.absolute)
    segments = [s for s in path.split("/") if s not in ("", ".")]
    if not segments:
        raise InvalidFilePathError(path, FilePathProblem.empty)
    for segment in segments:
        problem = _segment_problem(segment)
        if problem is not None:
            raise InvalidFilePathError(path, problem)
    normalized = "/".join(segments)
    if len(normalized.encode("utf-8")) > MAX_PATH_BYTES:
        raise InvalidFilePathError(path, FilePathProblem.too_long)
    return normalized
