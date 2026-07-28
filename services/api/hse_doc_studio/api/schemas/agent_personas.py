from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CreateAgentPersonaRequest(BaseModel):
    label: str
    instruction: str
    description: str = ""


class UpdateAgentPersonaRequest(BaseModel):
    # All optional: omitted (or null) field = keep current value (PATCH semantics).
    label: str | None = None
    description: str | None = None
    instruction: str | None = None


class AgentPersonaResponse(BaseModel):
    id: UUID
    label: str
    description: str
    instruction: str
    created_at: datetime


class BuiltinPersonaResponse(BaseModel):
    # A shipped preset role — read-only, but its instruction is exposed so the
    # Settings UI can show it and duplicate it into an editable custom role.
    id: str
    label: str
    description: str
    instruction: str
