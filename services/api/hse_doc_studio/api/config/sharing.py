"""Общий доступ: ссылки на проекты и гостевые сессии."""

from typing import Literal

from pydantic import BaseModel, Field


class SharingConfig(BaseModel):
    """Ссылки доступа к проектам. Заданные значения побеждают настройки админки и блокируют их правку."""

    links_enabled: bool | None = Field(
        default=None,
        description="Разрешить ссылки на проекты (по умолчанию да); заданное значение блокирует правку в админке.",
    )
    max_link_role: Literal["reader", "reviewer", "editor"] | None = Field(
        default=None,
        description="Предел роли по ссылке: reader, reviewer или editor (по умолчанию editor); блокирует правку.",
    )
    guest_session_days: int = Field(
        default=30, ge=1, le=365, description="Срок гостевой сессии по ссылке, суток (скользящий)."
    )
