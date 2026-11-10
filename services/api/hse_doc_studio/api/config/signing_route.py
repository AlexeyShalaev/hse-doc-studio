"""Маршрут подписания (docs/design/signing-route.md): автонапоминания подписантам (5.7) и сверка с проектом (5.5)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SigningRouteConfig(BaseModel):
    """Только серверный режим. Ручное «Напомнить» (раз в 12 часов на человека) здесь не настраивается."""

    reminder_interval_s: float = Field(
        default=900.0,
        ge=30,
        le=86400,
        description="Как часто сервер проверяет, кому из подписантов пора напомнить, в секундах.",
    )
    reminder_before_deadline_hours: float = Field(
        default=24.0,
        gt=0,
        le=720,
        description="За сколько часов до срока маршрута подписант, чья очередь, получает автонапоминание.",
    )
    reminder_waiting_days: float = Field(
        default=3.0,
        gt=0,
        le=90,
        description="Через сколько суток без запросов и напоминаний подписанту в очереди уходит автонапоминание.",
    )
    reminder_max_auto: int = Field(
        default=3,
        ge=0,
        le=20,
        description="Сколько автонапоминаний получает один подписант за одну отправку маршрута; 0 выключает их.",
    )
    sweep_interval_s: float = Field(
        default=300.0,
        ge=30,
        le=86400,
        description="Как часто сервер сверяет идущие маршруты подписания с документами проектов, в секундах.",
    )
