from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType

logger = structlog.get_logger()


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _to_dict(provider: AIProvider) -> dict[str, Any]:
    return {
        "id": str(provider.id),
        "name": provider.name,
        "type": str(provider.type),
        "api_key": provider.api_key,
        "base_url": provider.base_url,
        "models": list(provider.models),
        "created_at": provider.created_at.isoformat(),
        "ssl_verify": provider.ssl_verify,
        "connect_timeout_s": provider.connect_timeout_s,
        "request_timeout_s": provider.request_timeout_s,
    }


def _from_dict(data: dict[str, Any]) -> AIProvider:
    return AIProvider(
        id=UUID(data["id"]),
        name=data["name"],
        type=AIProviderType(data["type"]),
        api_key=data.get("api_key", ""),
        base_url=data.get("base_url", ""),
        models=list(data.get("models", [])),
        created_at=_parse_dt(data["created_at"]),
        # Defaults keep records written before these fields existed loadable.
        ssl_verify=bool(data.get("ssl_verify", True)),
        connect_timeout_s=float(data.get("connect_timeout_s", 10.0)),
        request_timeout_s=float(data.get("request_timeout_s", 60.0)),
    )


class JsonAIProviderRepository:
    """Persists configured AI providers to data_dir/ai_providers.json.

    A single JSON array of provider records, kept separate from config.json so
    API keys never leak into the general settings blob. Writes are atomic
    (temp file + os.replace) to avoid a half-written list on crash.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._path = data_dir / "ai_providers.json"

    def _read(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("ai_providers.json read error", path=str(self._path), exc=str(exc))
            return []
        return data if isinstance(data, list) else []

    def _write(self, items: list[dict[str, Any]]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
        logger.debug("ai_providers saved", path=str(self._path), count=len(items))

    def list_all(self) -> list[AIProvider]:
        out: list[AIProvider] = []
        for raw in self._read():
            try:
                out.append(_from_dict(raw))
            except Exception as exc:
                logger.warning("ai_providers.json skipped malformed record", exc=str(exc))
        return out

    def get(self, provider_id: UUID) -> AIProvider | None:
        return next((p for p in self.list_all() if p.id == provider_id), None)

    def create(self, provider: AIProvider) -> None:
        items = self._read()
        items.append(_to_dict(provider))
        self._write(items)

    def update(self, provider: AIProvider) -> None:
        items = self._read()
        target = str(provider.id)
        for idx, raw in enumerate(items):
            if raw.get("id") == target:
                items[idx] = _to_dict(provider)
                self._write(items)
                return
        # Caller (use case) checks existence first; reaching here means the
        # record vanished between read and write — persist it anyway.
        items.append(_to_dict(provider))
        self._write(items)

    def delete(self, provider_id: UUID) -> bool:
        items = self._read()
        target = str(provider_id)
        remaining = [raw for raw in items if raw.get("id") != target]
        if len(remaining) == len(items):
            return False
        self._write(remaining)
        return True
