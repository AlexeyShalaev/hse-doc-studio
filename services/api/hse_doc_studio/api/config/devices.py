from __future__ import annotations

from pydantic import BaseModel, Field


class DevicesConfig(BaseModel):
    """Только серверный режим: присутствие подключённых локальных Студий (docs/design/connected-devices.md)."""

    interval_s: int = Field(
        default=60, ge=10, le=600, description="Как часто локальная Студия шлёт сигнал присутствия, в секундах."
    )
    online_window_s: int = Field(
        default=180,
        ge=30,
        le=3600,
        description="Сколько секунд после последнего сигнала Студия считается онлайн (не меньше трёх интервалов).",
    )
    persist_interval_s: int = Field(
        default=120,
        ge=10,
        le=1800,
        description="Не чаще, чем раз в столько секунд сервер пишет неизменившееся присутствие в базу.",
    )
    retention_days: int = Field(
        default=60, ge=1, le=3650, description="Через сколько дней молчания устройство забывается."
    )
