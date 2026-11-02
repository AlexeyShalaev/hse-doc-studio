"""Самодиагностика сервера (HSE_STUDIO__DIAGNOSTICS__*). Пороги и уведомления правятся в админке."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiagnosticsConfig(BaseModel):
    enabled: bool = Field(default=True, description="Периодически проверять систему под лидерским локом.")
    interval_s: float = Field(default=300.0, ge=30, le=86_400, description="Как часто идёт плановая проверка.")
    check_timeout_s: float = Field(default=20.0, ge=1, le=300, description="Предел времени одной проверки.")
    public_endpoint: bool = Field(
        default=False,
        description="Открыть без входа GET /health/diagnostics с общим итогом и статусами проверок (без причин и "
        "значений) для внешнего мониторинга.",
    )
