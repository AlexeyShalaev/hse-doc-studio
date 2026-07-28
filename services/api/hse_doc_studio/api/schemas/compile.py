from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TriggerCompileResponse(BaseModel):
    compile_id: str


class CancelCompileResponse(BaseModel):
    cancelled_task: bool
    record_finalised: bool


class CompileListItemResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    id: str
    doc_id: str
    engine: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    pages: int | None
    words: int | None
    chars: int | None
    warnings: int
    errors: int


class CompileDetailResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    id: str
    doc_id: str
    engine: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    log: str
    pages: int | None
    words: int | None
    chars: int | None
    warnings: int
    errors: int
    check_results: list[dict[str, Any]]
