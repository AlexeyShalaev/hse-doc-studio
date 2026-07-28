from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.update.entities import ReleaseEntry, UpdateCheckState

logger = structlog.get_logger()

# Сколько релизов держим в кэше: столько же показывает и список версий в UI.
# Дальше в прошлое переключаться незачем, а файл не должен расти без конца.
MAX_CACHED_RELEASES = 30


class JsonUpdateCheckRepository:
    """Последний известный ответ фида релизов в data_dir/update-check.json.

    Отдельный файл, а не ключ в config.json: это кэш, а не настройка — в
    `GET /settings` и в экспорт настроек ему попадать нечего.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._path = data_dir / "update-check.json"

    def get(self) -> UpdateCheckState | None:
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return UpdateCheckState(
                checked_at=datetime.fromisoformat(str(raw["checked_at"])),
                releases=_parse_releases(raw),
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Битый кэш — это не повод отдать 500 на «О программе»: считаем, что
            # проверок ещё не было, следующая перезапишет файл.
            logger.warning("update-check.json read error", path=str(self._path), exc=str(exc))
            return None

    def save(self, state: UpdateCheckState) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "checked_at": state.checked_at.isoformat(),
            "releases": [
                {"version": release.version, "date": release.date, "notes": list(release.notes)}
                for release in state.releases[:MAX_CACHED_RELEASES]
            ],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("update check cached", latest=state.latest, count=len(state.releases))


def _parse_releases(raw: dict[str, Any]) -> tuple[ReleaseEntry, ...]:
    releases = raw.get("releases")
    if isinstance(releases, list):
        return tuple(
            ReleaseEntry(
                version=str(item["version"]),
                date=str(item.get("date") or ""),
                notes=tuple(str(note) for note in item.get("notes") or []),
            )
            for item in releases
            if isinstance(item, dict) and item.get("version")
        )
    # Файл, записанный сборкой, которая знала только про одну (последнюю) версию.
    # Номер в нём годный — терять его из-за смены формата незачем.
    latest = raw.get("latest")
    if isinstance(latest, str) and latest:
        return (
            ReleaseEntry(
                version=latest,
                date=str(raw.get("date") or ""),
                notes=tuple(str(note) for note in raw.get("notes") or []),
            ),
        )
    return ()
