"""Контракт статуса сборок проекта (docs/design/connected-devices.md, часть 3)."""

from __future__ import annotations

from datetime import datetime

from hse_doc_studio.api.schemas.common import StrictModel


class BuildOut(StrictModel):
    at: datetime
    commit: str | None
    pages: int | None
    # true: собран из текущей версии проекта; false: версия изменилась; null: коммит неизвестен.
    fresh: bool | None
    sha256: str | None
    size: int | None
    # Идентификатор облачной сборки (запись `last_compile_id` документа после синхронизации); у выгрузки Студии пусто.
    compile_id: str | None = None


class StudioBuildOut(BuildOut):
    artifact_id: str
    by_name: str | None


class DocumentBuildsOut(StrictModel):
    doc_id: str
    cloud: BuildOut | None
    cloud_running: bool
    cloud_failed_at: datetime | None
    studio: StudioBuildOut | None


class ProjectBuildsResponse(StrictModel):
    head: str | None
    dirty: bool
    documents: list[DocumentBuildsOut]
    max_pdf_bytes: int
