"""ИИ-шлюз сервера: повторы, автомат отказов, срок хранения журнала."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AiGatewayConfig(BaseModel):
    retries: int = Field(
        default=2, ge=0, le=5, description="Повторов временной ошибки провайдера, пока в поток ничего не ушло."
    )
    retry_base_delay_s: float = Field(
        default=0.5, gt=0, le=30, description="Первая пауза перед повтором, дальше вдвое."
    )
    retry_max_delay_s: float = Field(default=8.0, gt=0, le=120, description="Потолок паузы между повторами.")
    breaker_threshold: int = Field(
        default=5, ge=1, le=100, description="Подряд идущих сбоев, после которых провайдер закрывается на время."
    )
    breaker_open_s: float = Field(
        default=30.0, gt=0, le=3600, description="Сколько закрытый провайдер отказывает сразу, прежде чем его пробуют."
    )
    usage_retention_days: int = Field(
        default=90, ge=1, le=3650, description="Сколько дней хранится журнал вызовов шлюза (кто, куда, токены)."
    )
