from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.compile.failure import failure_message
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CheckSeverity, CompileStatus
from hse_doc_studio.core.events import IJobLogStream
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    ICompileRepository,
)

logger = structlog.get_logger()

STATUS_PREFIX = "__STATUS__:"
RESULT_PREFIX = "__RESULT__:"
# Как часто поток заглядывает в запись, пока сборка идёт без живой шины, и как долго ждёт итога.
RECORD_POLL_S = 0.5
MAX_WAIT_S = 2 * 60 * 60
_UNFINISHED = (CompileStatus.pending, CompileStatus.running)


def result_line(record: CompileRecord) -> str:
    """Итог сборки одной строкой для события `done`: страницы, замечания проверок и причина сбоя."""
    error = None
    if record.error_code is not None:
        error = {
            "code": record.error_code,
            "detail": record.error_detail,
            "message": failure_message(record.error_code, current_interface_language()),
        }
    payload = {
        "pages": record.pages,
        "warnings": sum(1 for r in record.check_results if r.severity == CheckSeverity.warn),
        "errors": sum(1 for r in record.check_results if r.severity == CheckSeverity.err),
        "error": error,
        # Места подписей из шаблона, которые встали по строкам этой сборки (signing-route.md, 15.17.9).
        "signature_places_moved": record.signature_places_moved or 0,
    }
    return RESULT_PREFIX + json.dumps(payload, ensure_ascii=False)


@dataclass
class GetCompileStreamInput:
    project_id: UUID
    doc_id: str
    compile_id: UUID


async def _enumerate(lines: AsyncIterator[str]) -> AsyncIterator[tuple[int, str]]:
    index = 0
    async for line in lines:
        yield index, line
        index += 1


class GetCompileStreamUC:
    """Returns an AsyncGenerator that yields log lines.

    If the build is still running (tracked by the in-memory log bus), the
    generator delivers lines as they arrive. Пока запись «идёт», а шины ещё
    нет (облачная сборка до первой строки раннера, гонка со стартом), поток
    ждёт итога, а не закрывается со статусом «pending». Once the bus closes
    or if the build was already finished before subscription, we fall back to
    the persisted record's log.
    """

    def __init__(
        self,
        locator: IProjectLocator,
        compile_repo: ICompileRepository,
        log_stream: IJobLogStream,
    ) -> None:
        self._locator = locator
        self._compile_repo = compile_repo
        self._log_stream = log_stream

    async def execute(self, inp: GetCompileStreamInput) -> AsyncGenerator[str, None]:
        project_folder = await self._locator.folder_of(inp.project_id)
        if project_folder is None:
            return _single(f"[error] project not found: {inp.project_id}")
        # Шина логов глобальна и знает только compile_id: сначала убеждаемся, что запись из проекта в URL.
        if await self._compile_repo.get_for_project(project_folder, inp.compile_id) is None:
            return _single(f"[error] compile record not found: {inp.compile_id}")
        return self._stream(project_folder, inp.compile_id)

    async def _stream(self, project_folder: Path, compile_id: UUID) -> AsyncGenerator[str, None]:
        seen: set[str] = set()
        cursor = _Cursor()
        record = await self._compile_repo.get_for_project(project_folder, compile_id)
        waited = 0.0
        while record is not None:
            # Live tail while the build is active.
            async for line in self._tail(compile_id, cursor):
                seen.add(line)
                yield line
            record = await self._compile_repo.get_for_project(project_folder, compile_id)
            # Закрытая шина значит, что производитель закончил: запись, застрявшая «идущей» (сбой в фазе
            # проверок), ждать бесполезно.
            if record is None or record.status not in _UNFINISHED or cursor.closed or waited >= MAX_WAIT_S:
                break
            await asyncio.sleep(RECORD_POLL_S)
            waited += RECORD_POLL_S

        async for line in _backfill(record, seen, compile_id):
            yield line

    async def _tail(self, compile_id: UUID, cursor: _Cursor) -> AsyncGenerator[str, None]:
        if not self._log_stream.has(compile_id):
            return
        # Шина воспроизводит буфер с начала на каждую подписку: уже выданное пропускаем.
        async for index, line in _enumerate(self._log_stream.subscribe(compile_id)):
            if index >= cursor.delivered:
                cursor.delivered = index + 1
                yield line
        cursor.closed = True


@dataclass
class _Cursor:
    delivered: int = 0
    closed: bool = False


async def _single(line: str) -> AsyncGenerator[str, None]:
    yield line


async def _backfill(record: CompileRecord | None, seen: set[str], compile_id: UUID) -> AsyncGenerator[str, None]:
    """Что не вошло в живой поток: строки записи сборки, затем статус и итог.

    After the bus closes (or if it was never active) this covers two cases: a subscriber that arrived after the
    build finished gets everything replayed; one that raced the producer at the very start gets the gap filled,
    so the final state is deterministic.
    """
    if record is None:
        if not seen:
            yield f"[error] compile record not found: {compile_id}"
        return
    for line in (record.log or "").splitlines():
        if line not in seen:
            yield line
    yield f"{STATUS_PREFIX}{record.status}"
    yield result_line(record)
