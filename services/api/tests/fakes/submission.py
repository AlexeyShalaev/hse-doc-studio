"""InMemory-реализации ports сдачи: репозиторий записей, архив пакетов и аудит скачиваний."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import PackSubmissionRecord
from hse_doc_studio.core.storage.models import PresignedUrl


class InMemoryPackSubmissionRepository:
    def __init__(self) -> None:
        self._records: dict[tuple[Path, UUID], PackSubmissionRecord] = {}

    async def list_for_project(self, project_folder: Path) -> list[PackSubmissionRecord]:
        found = [r for (folder, _), r in self._records.items() if folder == project_folder]
        return [replace(r) for r in sorted(found, key=lambda r: r.created_at)]

    async def get(self, project_folder: Path, submission_id: UUID) -> PackSubmissionRecord | None:
        record = self._records.get((project_folder, submission_id))
        return None if record is None else replace(record)

    async def save(self, record: PackSubmissionRecord) -> None:
        self._records[(record.project_folder, record.id)] = replace(record)


class FakeSubmissionArchive:
    def __init__(self, *, links: bool = True) -> None:
        self.objects: dict[str, bytes] = {}
        self.links = links

    @property
    def enabled(self) -> bool:
        return True

    async def put(self, project_id: UUID, submission_id: UUID, archive: Path, content_type: str) -> str:
        key = f"artifacts/{project_id}/submissions/{submission_id}/{archive.name}"
        self.objects[key] = archive.read_bytes()
        return key

    async def size(self, key: str) -> int | None:
        return len(self.objects[key]) if key in self.objects else None

    async def link(self, key: str) -> PresignedUrl | None:
        if key not in self.objects:
            raise FileNotFoundError(key)
        if not self.links:
            return None
        from datetime import datetime, timezone  # noqa: PLC0415

        return PresignedUrl(url=f"https://s3.test/{key}?sig=1", expires_at=datetime.now(tz=timezone.utc))

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        if key not in self.objects:
            raise FileNotFoundError(key)
        yield self.objects[key]


class RecordingSubmissionAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str | None, UUID, UUID, str]] = []

    async def downloaded(self, actor: Actor | None, project_id: UUID, submission_id: UUID, *, via: str) -> None:
        self.events.append((None if actor is None else actor.id, project_id, submission_id, via))
