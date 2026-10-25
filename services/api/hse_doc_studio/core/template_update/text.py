"""Сравнение файлов проекта и шаблона по смыслу, а не по байтам.

Студенты правят файлы и в Студии, и в VS Code на Windows: концы строк и BOM не
считаются правкой, а итог слияния пишется с концами строк пользователя. Архивы
Office (pptx) сравниваются по содержимому членов: байты zip зависят от версии
zlib контейнера или хоста.
"""

from __future__ import annotations

import difflib
import io
import re
import zipfile
from pathlib import PurePosixPath

_BOM = b"\xef\xbb\xbf"
_TEXT_SUFFIXES = frozenset(
    {".tex", ".md", ".html", ".htm", ".txt", ".cls", ".sty", ".bib", ".bst", ".yaml", ".yml", ".json", ".csv",
     ".css", ".js", ".j2", ".xml", ".svg", ".py"}
)  # fmt: skip
_ZIP_SUFFIXES = frozenset({".pptx", ".docx", ".xlsx"})
_SNIFF_BYTES = 8192


def is_binary(path: str, *contents: bytes | None) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return False
    if suffix in _ZIP_SUFFIXES:
        return True
    for content in contents:
        if content is None:
            continue
        if b"\x00" in content[:_SNIFF_BYTES]:
            return True
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            return True
    return False


def _split_bom(content: bytes) -> tuple[bool, bytes]:
    if content.startswith(_BOM):
        return True, content[len(_BOM) :]
    return False, content


def normalize_text(content: bytes) -> bytes:
    """Текст без BOM и с LF: так сравниваются и сливаются файлы."""
    _bom, body = _split_bom(content)
    return body.replace(b"\r\n", b"\n")


def restore_text_style(content: bytes, like: bytes | None) -> bytes:
    """Вернуть итогу концы строк и BOM файла пользователя `like`."""
    if like is None:
        return content
    had_bom, body = _split_bom(like)
    if b"\r\n" in body:
        content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return _BOM + content if had_bom else content


def _zip_members(content: bytes) -> dict[str, bytes] | None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return {info.filename: archive.read(info.filename) for info in archive.infolist()}
    except (zipfile.BadZipFile, OSError, ValueError):
        return None


def same_content(path: str, first: bytes | None, second: bytes | None) -> bool:
    """Одинаково ли содержимое по смыслу (концы строк, BOM, упаковка zip)."""
    if first is None or second is None:
        return first is second
    if first == second:
        return True
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in _ZIP_SUFFIXES:
        first_members = _zip_members(first)
        return first_members is not None and first_members == _zip_members(second)
    if is_binary(path, first, second):
        return False
    return normalize_text(first) == normalize_text(second)


_DIFF_LIMIT = 256_000


def unified_diff(path: str, old: bytes | None, new: bytes | None, old_label: str, new_label: str) -> tuple[str, bool]:
    """Унифицированный дифф текстового файла (без различия концов строк) и флаг усечения."""
    old_lines = normalize_text(old).decode("utf-8", "replace").splitlines(keepends=True) if old is not None else []
    new_lines = normalize_text(new).decode("utf-8", "replace").splitlines(keepends=True) if new is not None else []
    patch = "".join(
        difflib.unified_diff(old_lines, new_lines, fromfile=f"{old_label}/{path}", tofile=f"{new_label}/{path}")
    )
    if len(patch) > _DIFF_LIMIT:
        return patch[:_DIFF_LIMIT], True
    return patch, False


_MARKER_RE = re.compile(rb"^(?:<{7}|>{7})(?: |$)", re.MULTILINE)


def has_conflict_markers(content: bytes) -> bool:
    return _MARKER_RE.search(content) is not None
