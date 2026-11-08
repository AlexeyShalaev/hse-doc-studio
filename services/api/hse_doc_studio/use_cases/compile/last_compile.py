"""Последняя сборка документа, на которую можно сослаться в этой Студии.

`documents[].last_compile_id` лежит в project.json, а этот файл общий с другой стороной git-синхронизации. Перемотка,
клон и слияние, где менялась только чужая сторона, приносят файл целиком, и с ним идентификатор сборки, которая есть
только там (у облачной Студии в её журнале, у локальной в `.hse-studio/compiles`). Такой ссылке здесь не на что
указывать: `get_compile` отвечает «Не найдено», вкладки сборки и проверок пустеют.

Ссылка исправляется при чтении, а файл не правится. Правка ушла бы следующей синхронизацией на другую сторону, та
исправила бы ссылку по-своему, и стороны перекидывались бы коммитами без конца. Кроме того, получение облачного PDF
записывает сборку под облачным идентификатором (`devices/local_builds.py`): пришедшая ссылка тогда оживает сама.

У документа, который выпускается не в PDF (pptx), облачную сборку получить нельзя, и чужая ссылка живёт, пока одна
из сторон не соберёт его снова. Список документов читается на каждое обновление страницы, поэтому о такой ссылке
пишем в лог один раз за запуск (на документ и ссылку), а не на каждый запрос.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import Document
from hse_doc_studio.core.repositories import ICompileRepository

logger = structlog.get_logger()

# Уже записанные в лог чужие ссылки: (папка проекта, документ, ссылка). Предел страхует от роста на долгом запуске.
_REPORTED: set[tuple[Path, str, UUID]] = set()
_REPORTED_LIMIT = 4096


async def effective_last_compile_id(compiles: ICompileRepository | None, folder: Path, doc: Document) -> UUID | None:
    """Своя ссылка, если запись есть; иначе последняя сборка документа в этой Студии; иначе None.

    Сбой чтения журнала оставляет ссылку как есть: исправление вторично, список документов важнее.
    """
    pointer = doc.last_compile_id
    if pointer is None or compiles is None:
        return pointer
    try:
        if await compiles.get_for_project(folder, pointer) is not None:
            return pointer
        history = await compiles.list_for_document(folder, doc.id)
    except Exception:  # noqa: BLE001 — см. выше
        logger.warning("last compile pointer unreadable", doc_id=doc.id, exc_info=True)
        return pointer
    latest = max(history, key=lambda record: record.started_at, default=None)
    _report_foreign(folder, doc.id, pointer, latest.id if latest is not None else None)
    return latest.id if latest is not None else None


def _report_foreign(folder: Path, doc_id: str, pointer: UUID, replaced_by: UUID | None) -> None:
    """В лог только первая встреча чужой ссылки документа: повторы на каждом чтении списка ничего не добавляют."""
    key = (folder, doc_id, pointer)
    if key in _REPORTED:
        return
    if len(_REPORTED) >= _REPORTED_LIMIT:
        _REPORTED.clear()
    _REPORTED.add(key)
    logger.info(
        "last compile pointer is foreign",
        doc_id=doc_id,
        compile_id=str(pointer),
        replaced_by=str(replaced_by) if replaced_by is not None else None,
    )


async def with_effective_last_compile(compiles: ICompileRepository | None, folder: Path, doc: Document) -> Document:
    """Копия документа с исправленной ссылкой; тот же объект, если исправлять нечего."""
    pointer = await effective_last_compile_id(compiles, folder, doc)
    return doc if pointer == doc.last_compile_id else replace(doc, last_compile_id=pointer)
