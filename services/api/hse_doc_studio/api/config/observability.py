"""Здоровье и метрики сервера."""

from pydantic import BaseModel, Field, SecretStr


class ObservabilityConfig(BaseModel):
    """Токены для деталей /health/ready и для /metrics (HSE_STUDIO__OBSERVABILITY__*)."""

    health_token: SecretStr | None = Field(
        default=None,
        description="Bearer-токен, по которому /health/ready отдаёт детали проверок; без него детали только админу.",
    )
    metrics_token: SecretStr | None = Field(
        default=None,
        description="Bearer-токен для /metrics; без токена эндпоинт отвечает 404.",
    )
