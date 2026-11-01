"""InMemory-реализация ICompileRepository: записи по ключу (папка, id), порядок как у Json-репозитория."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus


class InMemoryCompileRepository:
    def __init__(self) -> None:
        self._records: dict[tuple[Path, UUID], CompileRecord] = {}

    async def get_for_project(self, project_folder: Path, compile_id: UUID) -> CompileRecord | None:
        record = self._records.get((project_folder, compile_id))
        return None if record is None else replace(record)

    async def list_for_document(self, project_folder: Path, doc_id: str) -> list[CompileRecord]:
        found = [r for (folder, _), r in self._records.items() if folder == project_folder and r.doc_id == doc_id]
        return [replace(r) for r in sorted(found, key=lambda r: r.started_at)]

    async def list_unfinished(self, project_folder: Path) -> list[CompileRecord]:
        return [
            replace(r)
            for (folder, _), r in self._records.items()
            if folder == project_folder and r.status in (CompileStatus.pending, CompileStatus.running)
        ]

    async def save(self, record: CompileRecord) -> None:
        self._records[(record.project_folder, record.id)] = replace(record)
