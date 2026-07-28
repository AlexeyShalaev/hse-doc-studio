"""(De)serialisation of an AIProvider to/from the export-bundle record shape.

Kept independent from the on-disk repo format on purpose: the export bundle is
a versioned, portable contract that must stay stable even if storage changes.
The two shapes happen to coincide today; this module is the bundle's authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from hse_doc_studio.core.entities import AgentPersona, AIProvider
from hse_doc_studio.core.enums import AIProviderType


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def provider_to_export_dict(provider: AIProvider) -> dict[str, Any]:
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


def provider_from_export_dict(data: dict[str, Any]) -> AIProvider:
    """Rebuild an AIProvider from a bundle record.

    ``id`` and ``created_at`` are preserved when present (so re-importing is
    idempotent and a settings ``default_ai_provider_id`` reference stays valid)
    and synthesised otherwise, keeping hand-written bundles importable.
    """
    raw_id = data.get("id")
    raw_created = data.get("created_at")
    return AIProvider(
        id=UUID(str(raw_id)) if raw_id else uuid4(),
        name=str(data["name"]),
        type=AIProviderType(str(data["type"])),
        api_key=str(data.get("api_key", "")),
        base_url=str(data.get("base_url", "")),
        models=[str(m) for m in data.get("models", [])],
        created_at=_parse_dt(str(raw_created)) if raw_created else datetime.now(timezone.utc),
        ssl_verify=bool(data.get("ssl_verify", True)),
        connect_timeout_s=float(data.get("connect_timeout_s", 10.0)),
        request_timeout_s=float(data.get("request_timeout_s", 60.0)),
    )


def persona_to_export_dict(persona: AgentPersona) -> dict[str, Any]:
    return {
        "id": str(persona.id),
        "label": persona.label,
        "description": persona.description,
        "instruction": persona.instruction,
        "created_at": persona.created_at.isoformat(),
    }


def persona_from_export_dict(data: dict[str, Any]) -> AgentPersona:
    """Rebuild an AgentPersona from a bundle record. ``id``/``created_at`` preserved
    when present (idempotent re-import), synthesised otherwise."""
    raw_id = data.get("id")
    raw_created = data.get("created_at")
    return AgentPersona(
        id=UUID(str(raw_id)) if raw_id else uuid4(),
        label=str(data["label"]),
        description=str(data.get("description", "")),
        instruction=str(data.get("instruction", "")),
        created_at=_parse_dt(str(raw_created)) if raw_created else datetime.now(timezone.utc),
    )
