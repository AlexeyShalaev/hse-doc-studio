"""Сборки документов проекта на сервере: что собрано, когда и из какого коммита (connected-devices.md, часть 3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class BuildStamp:
    """Итог облачной сборки без лога и проверок: то, что нужно для статуса и сравнения PDF."""

    compile_id: UUID
    doc_id: str
    finished_at: datetime
    pages: int | None
    source_commit: str | None
    sha256: str | None
    size: int | None
    actor_name: str | None = None


@dataclass(frozen=True)
class DocumentCloudState:
    """Последняя удачная облачная сборка документа, идёт ли новая и чем кончилась последняя неудачная."""

    doc_id: str
    last_ok: BuildStamp | None
    running: bool
    last_failed_at: datetime | None


class IBuildStampRepository(Protocol):
    async def states(self, project_id: UUID) -> list[DocumentCloudState]:
        """По одной записи на документ, у которого есть хоть одна сборка."""
        ...

    async def last_ok(self, project_id: UUID, doc_id: str) -> BuildStamp | None: ...
