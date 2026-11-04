"""Статус сборок проекта на сервере глазами локальной Студии (ответ `/git/-/projects/{id}/builds`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.git_remote.client import JsonObject


@dataclass(frozen=True)
class CloudBuild:
    at: datetime
    commit: str | None
    pages: int | None
    # True: собран из текущей версии проекта на сервере; False: версия изменилась; None: коммит неизвестен.
    fresh: bool | None
    sha256: str | None
    size: int | None
    compile_id: UUID | None = None


@dataclass(frozen=True)
class CloudDocument:
    doc_id: str
    cloud: CloudBuild | None
    cloud_running: bool
    # Последний PDF, выгруженный какой-либо Студией (в том числе этой).
    studio: CloudBuild | None


@dataclass(frozen=True)
class CloudBuilds:
    head: str | None
    dirty: bool
    max_pdf_bytes: int
    documents: tuple[CloudDocument, ...]

    def of(self, doc_id: str) -> CloudDocument | None:
        return next((d for d in self.documents if d.doc_id == doc_id), None)


def _dt(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _uuid(value: object) -> UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _build(raw: object) -> CloudBuild | None:
    if not isinstance(raw, dict):
        return None
    at = _dt(raw.get("at"))
    if at is None:
        return None
    fresh = raw.get("fresh")
    return CloudBuild(
        at=at,
        commit=_str(raw.get("commit")),
        pages=_int(raw.get("pages")),
        fresh=fresh if isinstance(fresh, bool) else None,
        sha256=_str(raw.get("sha256")),
        size=_int(raw.get("size")),
        compile_id=_uuid(raw.get("compile_id")),
    )


def parse_cloud_builds(raw: JsonObject) -> CloudBuilds:
    """Разбор ответа сервера: непонятные поля пропускаются, а не роняют Студию (сервер новее или старше)."""
    documents = raw.get("documents")
    items = documents if isinstance(documents, list) else []
    parsed: list[CloudDocument] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("doc_id"), str):
            continue
        parsed.append(
            CloudDocument(
                doc_id=item["doc_id"],
                cloud=_build(item.get("cloud")),
                cloud_running=item.get("cloud_running") is True,
                studio=_build(item.get("studio")),
            )
        )
    return CloudBuilds(
        head=_str(raw.get("head")),
        dirty=raw.get("dirty") is True,
        max_pdf_bytes=_int(raw.get("max_pdf_bytes")) or 100 * 1024 * 1024,
        documents=tuple(parsed),
    )
