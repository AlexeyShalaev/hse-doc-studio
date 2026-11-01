"""Проверка предела размера проекта вокруг записи файла."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.projects.usage import IProjectQuota
from hse_doc_studio.core.repositories import IFileRepository


async def reserve_write(
    quota: IProjectQuota,
    file_repo: IFileRepository,
    project_id: UUID,
    folder: Path,
    path: str,
    content: bytes,
    freed: int = 0,
) -> int:
    """Проверяет, что запись влезает в предел, и возвращает прирост размера (отрицательный, если файл уменьшился).

    `freed` - байты, которые та же операция освободит (например, удаляемый прежний файл): они не считаются прирастом.
    """
    if not quota.enabled:
        return 0
    delta = len(content) - (len(file_repo.read(folder, path)) if file_repo.exists(folder, path) else 0) - freed
    await quota.check_write(project_id, delta)
    return delta
