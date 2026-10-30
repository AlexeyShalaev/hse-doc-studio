"""Настройки установки в админке: название и адрес, сборка.

Форма зафиксирована эталонами `contracts/server/fixtures` раньше ручек: экраны SPA работают на
демо-мире, бэкенд реализует эти же тела. Значения, заданные окружением, помечены в `fields`
(`locked`): интерфейс показывает их только для чтения, запись отвечает `409 setting_locked`.
"""

from __future__ import annotations

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.api.schemas.session import SettingState


class AdminInstanceSettings(StrictModel):
    name: str
    public_url: str
    docs_url: str | None
    fields: dict[str, SettingState]


class UpdateAdminInstanceRequest(StrictModel):
    """Меняется только заданное (не null). Пустой `docs_url` убирает ссылку."""

    name: str | None = Field(default=None, max_length=120)
    public_url: str | None = Field(default=None, max_length=2048)
    docs_url: str | None = Field(default=None, max_length=2048)


class AdminBuildSettings(StrictModel):
    # Предел длительности одной сборки, секунды.
    timeout_s: int
    # Сколько суток хранятся результаты сборок.
    artifact_retention_days: int
    fields: dict[str, SettingState]


class UpdateAdminBuildRequest(StrictModel):
    timeout_s: int | None = Field(default=None, ge=30, le=3600)
    artifact_retention_days: int | None = Field(default=None, ge=1, le=365)
