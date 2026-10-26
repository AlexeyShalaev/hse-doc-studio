"""Актор запроса: кто обращается к API."""

from __future__ import annotations

from fastapi import Request

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.mode import StudioMode


async def resolve_actor(_request: Request) -> Actor:
    """Локальная установка одна, у неё один актор. Сессии и токены серверного режима появятся на втором этапе."""
    if settings.mode is StudioMode.local:
        return Actor.local()
    msg = "actor resolution for server mode is not implemented (stage 2 of collaboration)"
    raise RuntimeError(msg)
