"""Автомасштабирование раннеров: цикл и адаптеры оркестратора. Политика (границы, остывание) правится в админке."""

from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr


class AutoscaleConfig(BaseModel):
    interval_s: float = Field(
        default=15.0, ge=1, le=3600, description="Как часто цикл сверяет очередь с числом раннеров."
    )
    webhook_secret: SecretStr | None = Field(
        default=None,
        description="Секрет подписи HMAC-SHA256 для вызова внешнего оркестратора (заголовок X-Autoscale-Signature).",
    )
    webhook_timeout_s: float = Field(default=10.0, gt=0, le=120, description="Таймаут вызова внешнего оркестратора.")
    compose_project: str | None = Field(
        default=None, description="Имя проекта docker compose для режима compose (`-p`); пусто значит по умолчанию."
    )
    compose_file: str | None = Field(default=None, description="Файл compose для режима compose (`-f`).")
    compose_service: str = Field(default="runner", description="Сервис раннеров в compose, который масштабируется.")
    compose_timeout_s: float = Field(default=120.0, gt=0, le=1800, description="Таймаут команды docker compose.")
