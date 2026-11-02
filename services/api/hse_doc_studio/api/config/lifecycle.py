"""Жизненный цикл данных: фоновая очистка по реестру политик и контроль места (HSE_STUDIO__LIFECYCLE__*)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LifecycleConfig(BaseModel):
    """Сроки хранения правятся в админке («Хранение данных»); здесь только механика прогона и пробы места."""

    enabled: bool = Field(default=True, description="Включить фоновую очистку по реестру политик хранения.")
    interval_s: float = Field(default=3600.0, ge=60, description="Как часто сервер очищает источники роста по срокам.")
    batch_size: int = Field(default=2000, ge=100, le=100_000, description="Строк в одной пачке удаления.")
    run_budget_s: float = Field(
        default=120.0, ge=5, description="Сколько секунд один источник может чиститься за прогон; остаток на следующем."
    )
    batch_pause_s: float = Field(
        default=0.05, ge=0, description="Пауза между пачками удаления: ограничивает нагрузку на базу."
    )
    partition_months_ahead: int = Field(
        default=3, ge=1, le=12, description="На сколько месяцев вперёд заранее создаются партиции журналов."
    )
    probe_enabled: bool = Field(default=True, description="Следить за местом на томах и размером базы.")
    probe_interval_s: float = Field(default=300.0, ge=10, description="Как часто проверяется место на томах и в базе.")
    db_size_limit_bytes: int = Field(
        default=0,
        ge=0,
        description="Сколько места отведено базе Postgres (диск базы api не видит); 0 значит предел неизвестен "
        "и доля занятости базы не считается.",
    )
    safe_mode_enabled: bool = Field(
        default=True, description="При критической нехватке места отказывать в крупных загрузках вместо падения."
    )
