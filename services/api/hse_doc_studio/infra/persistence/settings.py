from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class JsonSettingsRepository:
    """Reads/writes application settings to data_dir/config.json."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._path = data_dir / "config.json"

    def get(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("config.json read error", path=str(self._path), exc=str(exc))
            return {}

    def save(self, settings: dict[str, Any]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("settings saved", path=str(self._path))
