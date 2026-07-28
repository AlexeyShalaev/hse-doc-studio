from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChangeLogEntryResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    id: str
    at: datetime
    kind: str
    doc_id: str | None
    summary: str
    note: str | None


class AddChangeLogEntryRequest(BaseModel):
    kind: str = "manual_note"
    doc_id: str | None = None
    summary: str
    note: str | None = None
