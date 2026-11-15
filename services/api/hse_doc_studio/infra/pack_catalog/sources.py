"""Источники каталога и их история на томе данных (порт ICatalogSourceRepository): `packs-store/.sources.json` и
`packs-store/.history.jsonl`.

Источники лежат рядом с хранилищем версий, а не в базе: каталог установки целиком (версии, активный каталог,
источники, история) переносится бэкапом тома и не может разойтись с ним после восстановления; локальная Студия и
сервер пользуются одним кодом. Запись под файловым замком (несколько процессов api), замена атомарная. История
только дописывается строками JSON; при чтении берутся последние строки нужного источника.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.pack_catalog.entities import (
    CatalogEvent,
    CatalogSource,
    EventAction,
    SourceError,
    SourceKind,
)
from hse_doc_studio.infra.pack_catalog.store import file_lock

logger = structlog.get_logger()

SOURCES_FILE = ".sources.json"
HISTORY_FILE = ".history.jsonl"
_LOCK = ".sources.lock"
_FILE_VERSION = 1
# История читается с конца файла: строк одного источника не больше этого числа за раз.
_HISTORY_SCAN = 5000

_Sources = list[CatalogSource]


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def source_to_json(source: CatalogSource) -> dict[str, Any]:
    return {
        "id": str(source.id),
        "kind": source.kind.value,
        "label": source.label,
        "created_at": _iso(source.created_at),
        "updated_at": _iso(source.updated_at),
        "created_by": source.created_by,
        "enabled": source.enabled,
        "replace_builtin": source.replace_builtin,
        "track": source.track,
        "packs_path": source.packs_path,
        "url": source.url,
        "ref": source.ref,
        "credential_id": None if source.credential_id is None else str(source.credential_id),
        "service_access_id": None if source.service_access_id is None else str(source.service_access_id),
        "insecure_http": source.insecure_http,
        "archive_digest": source.archive_digest,
        "archive_name": source.archive_name,
        "folder": source.folder,
        "workspace_id": None if source.workspace_id is None else str(source.workspace_id),
        "applied_revision": source.applied_revision,
        "applied_at": _iso(source.applied_at),
        "checked_revision": source.checked_revision,
        "checked_at": _iso(source.checked_at),
        "check_ok": source.check_ok,
        "pending_versions": source.pending_versions,
        "error": None if source.error is None else {"code": source.error.code, "detail": source.error.detail},
    }


def source_from_json(raw: dict[str, Any]) -> CatalogSource:
    created = _dt(raw.get("created_at")) or datetime.now(UTC)
    error = raw.get("error")
    pending = raw.get("pending_versions")
    check_ok = raw.get("check_ok")
    return CatalogSource(
        id=UUID(str(raw["id"])),
        kind=SourceKind(raw["kind"]),
        label=str(raw.get("label") or ""),
        created_at=created,
        updated_at=_dt(raw.get("updated_at")) or created,
        created_by=_text(raw.get("created_by")),
        enabled=bool(raw.get("enabled", True)),
        replace_builtin=bool(raw.get("replace_builtin", False)),
        track=bool(raw.get("track", False)),
        packs_path=str(raw.get("packs_path") or "."),
        url=_text(raw.get("url")),
        ref=_text(raw.get("ref")),
        credential_id=_uuid(raw.get("credential_id")),
        service_access_id=_uuid(raw.get("service_access_id")),
        insecure_http=bool(raw.get("insecure_http", False)),
        archive_digest=_text(raw.get("archive_digest")),
        archive_name=_text(raw.get("archive_name")),
        folder=_text(raw.get("folder")),
        workspace_id=_uuid(raw.get("workspace_id")),
        applied_revision=_text(raw.get("applied_revision")),
        applied_at=_dt(raw.get("applied_at")),
        checked_revision=_text(raw.get("checked_revision")),
        checked_at=_dt(raw.get("checked_at")),
        check_ok=check_ok if isinstance(check_ok, bool) else None,
        pending_versions=pending if isinstance(pending, int) else 0,
        error=SourceError(str(error["code"]), str(error.get("detail", "")))
        if isinstance(error, dict) and error.get("code")
        else None,
    )


def event_to_json(event: CatalogEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "source_id": str(event.source_id),
        "action": event.action.value,
        "at": _iso(event.at),
        "ok": event.ok,
        "actor_id": event.actor_id,
        "revision": event.revision,
        "summary": dict(event.summary),
    }


def event_from_json(raw: dict[str, Any]) -> CatalogEvent:
    summary = raw.get("summary")
    return CatalogEvent(
        id=UUID(str(raw["id"])),
        source_id=UUID(str(raw["source_id"])),
        action=EventAction(raw["action"]),
        at=_dt(raw.get("at")) or datetime.now(UTC),
        ok=bool(raw.get("ok", False)),
        actor_id=_text(raw.get("actor_id")),
        revision=_text(raw.get("revision")),
        summary=summary if isinstance(summary, dict) else {},
    )


# Псевдонимы: внутри класса имя `list` занято методом и в аннотациях означало бы его.
_Events = list[CatalogEvent]


class JsonCatalogSourceRepository:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._path = root / SOURCES_FILE
        self._history = root / HISTORY_FILE

    async def list(self) -> _Sources:
        return sorted(self._read(), key=lambda s: (s.created_at, str(s.id)))

    async def get(self, source_id: UUID) -> CatalogSource | None:
        return next((s for s in self._read() if s.id == source_id), None)

    async def add(self, source: CatalogSource) -> None:
        with self._locked():
            self._write([*self._read(), source])

    async def update(self, source: CatalogSource) -> None:
        with self._locked():
            items = self._read()
            if any(s.id == source.id for s in items):
                self._write([source if s.id == source.id else s for s in items])

    async def delete(self, source_id: UUID) -> bool:
        with self._locked():
            items = self._read()
            kept = [s for s in items if s.id != source_id]
            if len(kept) == len(items):
                return False
            self._write(kept)
            return True

    async def add_event(self, event: CatalogEvent) -> None:
        line = json.dumps(event_to_json(event), ensure_ascii=False, default=str)
        with self._locked(), self._history.open("a", encoding="utf-8") as out:
            out.write(line + "\n")

    async def events(self, source_id: UUID, *, limit: int) -> _Events:
        try:
            with self._history.open(encoding="utf-8") as handle:
                lines = deque(handle, maxlen=_HISTORY_SCAN)
        except FileNotFoundError:
            return []
        found: list[CatalogEvent] = []
        key = str(source_id)
        for line in reversed(lines):
            try:
                raw = json.loads(line)
                if raw.get("source_id") == key:
                    found.append(event_from_json(raw))
            except (ValueError, KeyError, TypeError):
                continue
            if len(found) >= limit:
                break
        return found

    def _locked(self) -> Any:
        self._root.mkdir(parents=True, exist_ok=True)
        return file_lock(self._root / _LOCK)

    def _read(self) -> _Sources:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            logger.warning("pack catalog: sources file is unreadable", path=str(self._path), exc=str(exc))
            return []
        items: _Sources = []
        for raw in data.get("sources", []) if isinstance(data, dict) else []:
            try:
                items.append(source_from_json(raw))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("pack catalog: source record skipped", exc=str(exc))
        return items

    def _write(self, items: _Sources) -> None:
        body = json.dumps(
            {"version": _FILE_VERSION, "sources": [source_to_json(s) for s in items]}, ensure_ascii=False, indent=2
        )
        handle, name = tempfile.mkstemp(prefix=".sources.", suffix=".tmp", dir=self._root)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                out.write(body)
            os.replace(name, self._path)
        finally:
            Path(name).unlink(missing_ok=True)
