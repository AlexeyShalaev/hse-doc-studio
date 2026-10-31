"""Журнал вызовов ИИ-шлюза (аудит) и его сводка для админки."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class AiOperation(StrEnum):
    turn = "turn"
    models = "models"


class AiOutcome(StrEnum):
    ok = "ok"
    error = "error"
    denied = "denied"
    unavailable = "unavailable"


@dataclass(frozen=True)
class AiUsageRecord:
    """Один вызов. Тел запросов и ответов здесь нет: в них исходники пользователя."""

    id: UUID
    at: datetime
    user_id: str | None
    org_id: str | None
    project_id: UUID | None
    provider_id: UUID
    provider_owner: str
    model: str
    operation: AiOperation
    input_tokens: int
    output_tokens: int
    outcome: AiOutcome
    error_code: str | None
    duration_ms: int
    # Вошёл ли расход в квоту токенов (только общий провайдер).
    counted: bool


@dataclass(frozen=True)
class ProviderUsageSummary:
    provider_id: UUID
    calls: int
    errors: int
    denied: int
    input_tokens: int
    output_tokens: int


class IAiUsageLog(Protocol):
    async def record(self, item: AiUsageRecord) -> None: ...

    async def summary(self, since: datetime) -> list[ProviderUsageSummary]:
        """По провайдерам с начала `since`."""
        ...

    async def prune(self, before: datetime) -> int: ...
