"""Настройки облачных сборок локальной Студии: `data_dir/remote_runner.json` с правами 0600.

Секретов в файле нет: токен регистрации живёт только в памяти до регистрации, токен раннера
лежит в `identity.json` каталога раннера. Права узкие всё равно: адрес сервера и выбор
моделей это сведения о человеке.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.remote_runner import (
    REMOTE_RUNNER_MAX_CONCURRENCY,
    RemoteAiEndpointChoice,
    RemoteRunnerSettings,
)

logger = structlog.get_logger(__name__)

SETTINGS_FILE = "remote_runner.json"


def _to_dict(settings: RemoteRunnerSettings) -> dict[str, Any]:
    return {
        "enabled": settings.enabled,
        "server_url": settings.server_url,
        "name": settings.name,
        "concurrency": settings.concurrency,
        "yield_to_local": settings.yield_to_local,
        "ai_endpoints": [{"name": e.name, "provider_id": e.provider_id} for e in settings.ai_endpoints],
    }


def _from_dict(data: dict[str, Any]) -> RemoteRunnerSettings:
    concurrency = int(data.get("concurrency", 1))
    endpoints = tuple(
        RemoteAiEndpointChoice(name=str(item["name"]), provider_id=str(item["provider_id"]))
        for item in data.get("ai_endpoints", [])
        if isinstance(item, dict)
    )
    server_url = data.get("server_url")
    name = data.get("name")
    return RemoteRunnerSettings(
        enabled=bool(data.get("enabled", False)),
        server_url=str(server_url) if server_url else None,
        name=str(name) if name else None,
        # Файл правят руками: значение вне пределов не роняет Студию, а приводится к допустимому.
        concurrency=min(max(concurrency, 1), REMOTE_RUNNER_MAX_CONCURRENCY),
        yield_to_local=bool(data.get("yield_to_local", True)),
        ai_endpoints=endpoints,
    )


class JsonRemoteRunnerSettingsStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / SETTINGS_FILE

    async def load(self) -> RemoteRunnerSettings:
        return await asyncio.to_thread(self._load)

    async def save(self, settings: RemoteRunnerSettings) -> None:
        await asyncio.to_thread(self._save, settings)

    def _load(self) -> RemoteRunnerSettings:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return RemoteRunnerSettings()
        except (OSError, ValueError) as exc:
            logger.warning("remote_runner.json unreadable, using defaults", error=str(exc))
            return RemoteRunnerSettings()
        if not isinstance(data, dict):
            return RemoteRunnerSettings()
        try:
            return _from_dict(data)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("remote_runner.json malformed, using defaults", error=str(exc))
            return RemoteRunnerSettings()

    def _save(self, settings: RemoteRunnerSettings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        # Файл создаётся сразу с 0600: между записью и chmod он не бывает читаемым для всех.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(_to_dict(settings), handle, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        tmp.replace(self._path)
