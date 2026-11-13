"""Сроки контрольных точек (docs/design/signing-route.md, раздел 16): напоминание автору `checkpoint_due` (16.7)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from hse_doc_studio.core.checkpoint_deadlines import REMINDER_DAYS


class CheckpointConfig(BaseModel):
    """Только серверный режим: локальная Студия срок показывает и правит, но не напоминает."""

    reminder_days: int = Field(
        default=REMINDER_DAYS,
        ge=0,
        le=30,
        description="За сколько суток до срока контрольной точки владелец и авторы получают напоминание, если пакет "
        "точки ещё не собран; 0 выключает напоминание.",
    )
    reminder_interval_s: float = Field(
        default=900.0,
        ge=30,
        le=86400,
        description="Как часто сервер проверяет, кому пора напомнить о сроке контрольной точки, в секундах.",
    )
