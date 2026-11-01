"""Архивы пакетов сдачи в объектном хранилище и запись скачиваний в аудит."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.storage import InvalidObjectKeyError, ObjectNotFoundError, validate_key
from hse_doc_studio.core.storage.models import PresignedUrl
from hse_doc_studio.core.storage.ports import IObjectStore

LINK_TTL_S = 120
AUDIT_DOWNLOADED = "submission.downloaded"


def submission_key(project_id: UUID, submission_id: UUID, name: str) -> str:
    """`artifacts/<project_id>/submissions/<submission_id>/<имя архива>`."""
    return validate_key(f"artifacts/{project_id}/submissions/{submission_id}/{name}")


class ObjectSubmissionArchive:
    def __init__(self, objects: IObjectStore, *, link_ttl_s: int = LINK_TTL_S) -> None:
        self._objects = objects
        self._link_ttl_s = link_ttl_s

    @property
    def enabled(self) -> bool:
        return True

    async def put(self, project_id: UUID, submission_id: UUID, archive: Path, content_type: str) -> str:
        key = submission_key(project_id, submission_id, archive.name)
        with archive.open("rb") as handle:
            await self._objects.put(key, handle, content_type=content_type)
        return key

    async def size(self, key: str) -> int | None:
        return await self._head(key)

    async def link(self, key: str) -> PresignedUrl | None:
        link = await self._objects.presign_get(self._valid(key), expires_in_s=self._link_ttl_s)
        if link is None:
            return None
        if await self._head(key) is None:
            raise FileNotFoundError(key)
        return link

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._objects.stream(self._valid(key)):
                yield chunk
        except ObjectNotFoundError as exc:
            raise FileNotFoundError(key) from exc

    async def _head(self, key: str) -> int | None:
        info = await self._objects.head(self._valid(key))
        return None if info is None else info.size

    @staticmethod
    def _valid(key: str) -> str:
        try:
            return validate_key(key)
        except InvalidObjectKeyError as exc:
            raise FileNotFoundError(key) from exc


class AuditSubmissionDownloads:
    def __init__(self, audit: IAuditLog) -> None:
        self._audit = audit

    async def downloaded(self, actor: Actor | None, project_id: UUID, submission_id: UUID, *, via: str) -> None:
        await self._audit.record(
            AUDIT_DOWNLOADED,
            actor_id=None if actor is None else actor.id,
            target=str(submission_id),
            details={"project_id": str(project_id), "via": via},
        )
