"""Наблюдатель за готовыми PDF локальной сборки: выгрузка на сервер Студии (docs/design/local-sync.md, P7)."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class IBuiltPdfObserver(Protocol):
    def on_pdf_built(self, project_id: UUID, doc_id: str, pages: int | None) -> None:
        """Сборка документа удалась и PDF лежит на месте. Не блокирует и не бросает: сборка от этого не зависит."""
        ...


class NoopBuiltPdfObserver:
    """Серверный режим и всё, где выгружать некуда: PDF остаётся там, где собран."""

    def on_pdf_built(self, project_id: UUID, doc_id: str, pages: int | None) -> None:
        return None
