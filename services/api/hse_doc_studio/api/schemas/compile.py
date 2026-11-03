from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.api.schemas.personal_runners import CompilePlacement
from hse_doc_studio.api.schemas.session import CompileWait


class BuildAvailabilityResponse(StrictModel):
    """Есть ли сейчас кому собирать документы проекта.

    `cloud`: сборку берут раннеры сервера (локально false, ограничений нет); `any_runner`: подключён хотя бы
    один живой раннер; `tags`: теги сборки (`tex`, `office`), для которых исполнитель есть сейчас.
    Документ собирается, если его `build_tags` входят в `tags`.
    """

    cloud: bool
    any_runner: bool
    tags: list[str]


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
    # Только серверный режим: почему сборка не идёт (очередь, нет раннера, заменена). В локальном null.
    wait: CompileWait | None = None
    # Только серверный режим: где идёт сборка (общий раннер, свой раннер или раннер владельца). В локальном null.
    placement: CompilePlacement | None = None
