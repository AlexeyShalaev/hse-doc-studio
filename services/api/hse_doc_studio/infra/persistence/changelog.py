from __future__ import annotations

import json
from pathlib import Path

import structlog

from hse_doc_studio.core.entities import ChangeLogEntry
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_changelog_entry,
    serialize_changelog_entry,
)

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"


class JsonChangeLogRepository:
    """Reads/writes changelog to <folder>/.hse-studio/history.json."""

    def _path(self, project_folder: Path) -> Path:
        return project_folder / _HSE_STUDIO / "history.json"

    def _load_all(self, project_folder: Path) -> list[ChangeLogEntry]:
        path = self._path(project_folder)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [deserialize_changelog_entry(item) for item in raw]
        except Exception as exc:
            logger.warning("history.json read error", folder=str(project_folder), exc=str(exc))
            return []

    def list(self, project_folder: Path, doc_id: str | None = None) -> list[ChangeLogEntry]:
        entries = self._load_all(project_folder)
        if doc_id is None:
            return entries
        return [e for e in entries if e.doc_id == doc_id]

    def append(self, project_folder: Path, entry: ChangeLogEntry) -> None:
        entries = self._load_all(project_folder)
        entries.append(entry)
        studio_dir = project_folder / _HSE_STUDIO
        studio_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(project_folder)
        data = [serialize_changelog_entry(e) for e in entries]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("changelog entry appended", folder=str(project_folder), kind=str(entry.kind))
