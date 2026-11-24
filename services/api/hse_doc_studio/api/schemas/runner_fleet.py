"""Обновление всех раннеров установки разом (`/api/admin/runner-install/fleet`). Секретов и адресов установок нет."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel

FleetKindName = Literal["docker", "kubernetes", "ssh", "manual"]
ManualReasonName = Literal["helm", "container", "host", "unknown"]
FleetItemStateName = Literal["pending", "waiting", "running", "succeeded", "failed", "skipped"]


class FleetRunnerInfo(StrictModel):
    """Устаревший раннер; `kind=manual`: Студия его сама не обновит, `manual_reason` подсказывает, что делать."""

    runner_id: str
    name: str
    kind: FleetKindName
    version: str
    target_version: str
    status: str
    # Сколько сборок раннер выполняет сейчас: с идущей сборкой его обновят после неё.
    running_jobs: int
    manual_reason: ManualReasonName | None = None


class FleetItemInfo(StrictModel):
    runner_id: str
    name: str
    kind: FleetKindName
    from_version: str
    to_version: str
    state: FleetItemStateName
    # Причина для `failed` и `skipped`: busy, cancelled, install_busy, reconnect_timeout, job_timeout и коды установки.
    code: str | None = None
    detail: str = ""
    # Неудачное обновление: прежнюю версию вернули (true), не вернули (false) или откатывать было нечего (null).
    rolled_back: bool | None = None


class FleetBatchInfo(StrictModel):
    id: str
    state: Literal["running", "finished"]
    target_version: str
    created_at: datetime
    finished_at: datetime | None = None
    cancel_requested: bool
    items: list[FleetItemInfo]


class FleetPlanResponse(StrictModel):
    server_version: str
    # Показывать предложение: есть что обновлять и оно не отклонено для этой версии, либо идёт запуск.
    offer: bool
    dismissed_version: str | None = None
    items: list[FleetRunnerInfo]
    # Идущий запуск, если он есть (после перезагрузки страницы ход виден снова).
    batch: FleetBatchInfo | None = None


class FleetUpgradeRequest(StrictModel):
    runner_ids: list[str] = Field(min_length=1, max_length=200)


class FleetDismissRequest(StrictModel):
    version: str = Field(min_length=1, max_length=64)
