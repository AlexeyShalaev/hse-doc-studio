"""Состояние обновлений шаблона на диске проекта.

* `.hse-studio/template.json` — история обновлений и снятые с отслеживания файлы.
  Лежит в истории версий вместе с остальным состоянием: откат проекта к снимку
  откатывает и её, так что история обновлений всегда согласована с файлами.
* `.hse-studio/update/journal.json` — журнал идущей операции: обновления шаблона
  или применения слияния синхронизации (`kind`). Вне истории версий
  (core.vcs.constants): он описывает саму транзакцию и после неё удаляется.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.template_update.entities import (
    TemplateTrackingState,
    TemplateUpdateRecord,
    UpdateJournal,
    UpdateJournalKind,
    UpdateJournalState,
)
from hse_doc_studio.infra.persistence.project import assert_project_writable, read_json_or_none
from hse_doc_studio.infra.persistence.unknown_fields import Struct, preserve_unknown

logger = structlog.get_logger()

_HSE_STUDIO = ".hse-studio"
TRACKING_FILE = "template.json"
JOURNAL_DIR = "update"
JOURNAL_FILE = "journal.json"
BACKUP_DIR = "backup"

_TRACKING_SHAPE = Struct()


def _atomic_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def _record_from_json(raw: Any) -> TemplateUpdateRecord | None:
    if not isinstance(raw, dict):
        return None
    try:
        return TemplateUpdateRecord(
            id=str(raw["id"]),
            from_version=str(raw["from_version"]),
            to_version=str(raw["to_version"]),
            at=str(raw.get("at", "")),
            pre_commit=str(raw["pre_commit"]),
            commit=raw.get("commit"),
            markers=tuple(str(p) for p in raw.get("markers", ())),
            reverted=bool(raw.get("reverted", False)),
            reverts=raw.get("reverts"),
        )
    except (KeyError, TypeError):
        return None


def _record_to_json(record: TemplateUpdateRecord) -> dict[str, Any]:
    data = asdict(record)
    data["markers"] = list(record.markers)
    return data


class JsonTemplateTrackingRepository:
    def _path(self, folder: Path) -> Path:
        return folder / _HSE_STUDIO / TRACKING_FILE

    def get(self, folder: Path) -> TemplateTrackingState:
        raw = read_json_or_none(self._path(folder))
        if not isinstance(raw, dict):
            return TemplateTrackingState()
        history = tuple(r for r in (_record_from_json(item) for item in raw.get("history", ())) if r is not None)
        ignored = frozenset(str(p) for p in raw.get("ignored", ()) if isinstance(p, str))
        return TemplateTrackingState(ignored=ignored, history=history)

    def save(self, folder: Path, state: TemplateTrackingState) -> None:
        assert_project_writable(folder)
        path = self._path(folder)
        data = {
            "ignored": sorted(state.ignored),
            "history": [_record_to_json(record) for record in state.history],
        }
        _atomic_write(path, preserve_unknown(data, read_json_or_none(path), _TRACKING_SHAPE))


class JsonUpdateJournalRepository:
    def _dir(self, folder: Path) -> Path:
        return folder / _HSE_STUDIO / JOURNAL_DIR

    def _path(self, folder: Path) -> Path:
        return self._dir(folder) / JOURNAL_FILE

    def get(self, folder: Path) -> UpdateJournal | None:
        raw = read_json_or_none(self._path(folder))
        if not isinstance(raw, dict):
            return None
        try:
            return UpdateJournal(
                id=str(raw["id"]),
                state=UpdateJournalState(raw["state"]),
                from_version=str(raw["from_version"]),
                to_version=str(raw["to_version"]),
                pre_commit=str(raw["pre_commit"]),
                base_commit=raw.get("base_commit"),
                touched_paths=tuple(str(p) for p in raw.get("touched_paths", ())),
                added_paths=tuple(str(p) for p in raw.get("added_paths", ())),
                started_at=str(raw.get("started_at", "")),
                reverts=raw.get("reverts"),
                kind=UpdateJournalKind(raw.get("kind", UpdateJournalKind.template.value)),
                merge_parent=raw.get("merge_parent"),
                sync_id=raw.get("sync_id"),
            )
        except (KeyError, ValueError, TypeError):
            logger.warning("template update journal unreadable", folder=str(folder))
            return None

    def save(self, folder: Path, journal: UpdateJournal) -> None:
        data = asdict(journal)
        data["state"] = journal.state.value
        data["kind"] = journal.kind.value
        data["touched_paths"] = list(journal.touched_paths)
        data["added_paths"] = list(journal.added_paths)
        _atomic_write(self._path(folder), data)

    def backup(self, folder: Path, rel_paths: Iterable[str]) -> None:
        backup_root = self._dir(folder) / BACKUP_DIR
        for rel in rel_paths:
            source = folder / rel
            if source.is_file():
                target = backup_root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def restore(self, folder: Path, rel_path: str) -> bool:
        source = self._dir(folder) / BACKUP_DIR / rel_path
        if not source.is_file():
            return False
        target = folder / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return True

    def clear(self, folder: Path) -> None:
        shutil.rmtree(self._dir(folder), ignore_errors=True)

    def list_active(self, folders: Iterable[Path]) -> list[Path]:
        return [folder for folder in folders if self._path(folder).exists()]
