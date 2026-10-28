"""Ограничение частоты запросов."""

from pydantic import BaseModel, Field


class RateLimitConfig(BaseModel):
    """Лимиты общего сервера (HSE_STUDIO__RATE_LIMIT__*). В режиме local не применяются."""

    enabled: bool = Field(default=True, description="Включить ограничение частоты (счётчики по реплике api).")
    scale: float = Field(
        default=1.0,
        gt=0,
        description="Множитель лимитов: больше 1 ослабляет (организация за одним NAT), меньше 1 ужесточает.",
    )
