from __future__ import annotations

import json
from pathlib import Path

import structlog

logger = structlog.get_logger()


class JsonProjectIndexRepository:
    """Reads/writes known project paths to data_dir/projects.json."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._path = data_dir / "projects.json"

    def _load(self) -> list[str]:
        if not self._path.exists():
            return []
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("projects.json read error", exc=str(exc))
            return []

    def _save(self, entries: list[str]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_known(self) -> list[Path]:
        return [Path(p) for p in self._load()]

    def register(self, folder: Path) -> None:
        entries = self._load()
        folder_str = str(folder)
        if folder_str not in entries:
            entries.append(folder_str)
            self._save(entries)

    def unregister(self, folder: Path) -> None:
        entries = self._load()
        folder_str = str(folder)
        updated = [e for e in entries if e != folder_str]
        if len(updated) != len(entries):
            self._save(updated)
