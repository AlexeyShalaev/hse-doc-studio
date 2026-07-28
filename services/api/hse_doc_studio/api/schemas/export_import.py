from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    include_settings: bool = True
    include_ai_providers: bool = True
    include_agent_personas: bool = True
    # When set, provider api_keys are encrypted (PBKDF2 + Fernet) under this password.
    encryption_password: str | None = None


class ExportBundle(BaseModel):
    """The downloadable export file; also the body the import endpoint accepts."""

    version: str
    exported_at: datetime
    encrypted: bool
    settings: dict[str, Any] | None = None
    ai_providers: list[dict[str, Any]] = Field(default_factory=list)
    agent_personas: list[dict[str, Any]] = Field(default_factory=list)


class ImportRequest(ExportBundle):
    merge_strategy: str = "skip"  # "skip" | "replace"
    decryption_password: str | None = None


class ImportResponse(BaseModel):
    settings_imported: bool
    ai_providers_imported: int
    ai_providers_skipped: int
    agent_personas_imported: int
    agent_personas_skipped: int
    errors: list[str]
