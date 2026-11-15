"""Какой PDF в папке проекта собран Студией, а какой положил пользователь.

Сборка кладёт PDF рядом с исходником под тем же именем (`vkr/vkr.tex` даёт `vkr/vkr.pdf`). Такой PDF
пересоздаётся на каждой сборке и в историю идёт только с `track_pdf`. PDF без исходника рядом (рисунок,
скан, приложение, загруженное с компьютера) является работой пользователя и попадает в снимки
и синхронизацию, как любой другой файл. Дерево файлов в интерфейсе прячет PDF по тому же правилу.

PDF под `.hse-studio/` (замороженные копии подписей и подписанные PDF) живут своим порядком: в историю
их добавляет только явный `force_paths` синхронизации, поэтому без `track_pdf` они исключены, как раньше.
"""

from __future__ import annotations

from collections.abc import Callable

# Исходники, рядом с которыми сборка оставляет одноимённый PDF.
BUILD_PDF_SOURCE_SUFFIXES = (
    ".tex",
    ".docx",
    ".doc",
    ".odt",
    ".rtf",
    ".pptx",
    ".ppt",
    ".odp",
    ".md",
    ".html",
    ".htm",
)
_PDF = ".pdf"
_SERVICE_DIR = ".hse-studio/"


def is_build_output_pdf(path: str, is_file: Callable[[str], bool]) -> bool:
    """`path` (POSIX от корня проекта) это PDF, рядом с которым лежит одноимённый исходник."""
    if not path.endswith(_PDF):
        return False
    stem = path[: -len(_PDF)]
    return any(is_file(stem + suffix) for suffix in BUILD_PDF_SOURCE_SUFFIXES)


def is_pdf_outside_history(path: str, is_file: Callable[[str], bool]) -> bool:
    """PDF, который без `track_pdf` в историю не идёт: собранный или служебный под `.hse-studio/`."""
    if not path.endswith(_PDF):
        return False
    return path.startswith(_SERVICE_DIR) or is_build_output_pdf(path, is_file)
