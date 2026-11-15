"""Что известно о сборке документа для интерфейса: итог последней сборки и есть ли выпущенный файл.

Статус документа `err` значит две разные вещи: сборка упала (PDF нет или он от прошлой сборки) или сборка прошла,
а проверки нашли ошибки (PDF свежий). По одному статусу превью их не различало и вместо готового PDF показывало
заглушку «ещё не компилировался». Поэтому рядом со статусом отдаём итог записи последней сборки и наличие файла.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from hse_doc_studio.core.entities import CompileRecord, Document
from hse_doc_studio.core.enums import CompileStatus
from hse_doc_studio.core.repositories import ICompileRepository

logger = structlog.get_logger()


@dataclass(frozen=True)
class DocumentBuildView:
    # Итог записи `last_compile_id`; None, если сборок не было или запись не читается.
    last_compile_status: CompileStatus | None = None
    # Выпущенный файл документа лежит в проекте (PDF последней удачной сборки, pptx, загруженный файл).
    output_available: bool = False


async def last_compile_record(compiles: ICompileRepository | None, folder: Path, doc: Document) -> CompileRecord | None:
    """Запись `last_compile_id`; сбой чтения журнала даёт None: сведения о сборке вторичны для списка документов."""
    if compiles is None or doc.last_compile_id is None:
        return None
    try:
        return await compiles.get_for_project(folder, doc.last_compile_id)
    except Exception:  # noqa: BLE001 — см. выше
        logger.warning("document build view: compile record unreadable", doc_id=doc.id, exc_info=True)
        return None


def output_available(folder: Path, output_file: str | None) -> bool:
    """Файл результата на месте. Путь из резолва пака или загрузки; выход за папку проекта не считается файлом."""
    if not output_file:
        return False
    try:
        root = folder.resolve()
        target = (root / output_file).resolve()
        return target.is_relative_to(root) and target.is_file()
    except (OSError, ValueError):
        return False


def build_view_of(record: CompileRecord | None, folder: Path, output_file: str | None) -> DocumentBuildView:
    return DocumentBuildView(
        last_compile_status=record.status if record is not None else None,
        output_available=output_available(folder, output_file),
    )
