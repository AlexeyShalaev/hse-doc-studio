from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import AgentPersona

logger = structlog.get_logger()


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _to_dict(persona: AgentPersona) -> dict[str, Any]:
    return {
        "id": str(persona.id),
        "label": persona.label,
        "description": persona.description,
        "instruction": persona.instruction,
        "created_at": persona.created_at.isoformat(),
    }


def _from_dict(data: dict[str, Any]) -> AgentPersona:
    return AgentPersona(
        id=UUID(data["id"]),
        label=data["label"],
        description=data.get("description", ""),
        instruction=data.get("instruction", ""),
        created_at=_parse_dt(data["created_at"]),
    )


class JsonAgentPersonaRepository:
    """Persists user-defined agent roles to data_dir/agent_personas.json.

    A single JSON array of role records, kept next to ai_providers.json. Writes
    are atomic (temp file + os.replace) to avoid a half-written list on crash.
    Mirrors JsonAIProviderRepository.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._path = data_dir / "agent_personas.json"

    def _read(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("agent_personas.json read error", path=str(self._path), exc=str(exc))
            return []
        return data if isinstance(data, list) else []

    def _write(self, items: list[dict[str, Any]]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
        logger.debug("agent_personas saved", path=str(self._path), count=len(items))

    def list_all(self) -> list[AgentPersona]:
        out: list[AgentPersona] = []
        for raw in self._read():
            try:
                out.append(_from_dict(raw))
            except Exception as exc:
                logger.warning("agent_personas.json skipped malformed record", exc=str(exc))
        return out

    def get(self, persona_id: UUID) -> AgentPersona | None:
        return next((p for p in self.list_all() if p.id == persona_id), None)

    def create(self, persona: AgentPersona) -> None:
        items = self._read()
        items.append(_to_dict(persona))
        self._write(items)

    def update(self, persona: AgentPersona) -> None:
        items = self._read()
        target = str(persona.id)
        for idx, raw in enumerate(items):
            if raw.get("id") == target:
                items[idx] = _to_dict(persona)
                self._write(items)
                return
        # Caller (use case) checks existence first; reaching here means the
        # record vanished between read and write — persist it anyway.
        items.append(_to_dict(persona))
        self._write(items)

    def delete(self, persona_id: UUID) -> bool:
        items = self._read()
        target = str(persona_id)
        remaining = [raw for raw in items if raw.get("id") != target]
        if len(remaining) == len(items):
            return False
        self._write(remaining)
        return True
