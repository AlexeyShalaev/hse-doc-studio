"""Подключение к Postgres."""

from pydantic import BaseModel, Field


class DbConfig(BaseModel):
    """Postgres серверного режима (HSE_STUDIO__DB__*)."""

    dsn: str | None = Field(
        default=None,
        description="DSN Postgres, например postgresql+asyncpg://user:pass@host:5432/db; без драйвера берётся asyncpg.",
    )
    auto_migrate: bool = Field(
        default=False,
        description="Мигрировать схему на старте под advisory-локом (compose); в helm выключено, мигрирует job.",
    )
    pool_size: int = Field(default=10, ge=1, description="Размер пула соединений.")
    max_overflow: int = Field(default=10, ge=0, description="Сверх пула в пике.")
    echo: bool = Field(default=False, description="Печатать SQL (только для отладки).")
