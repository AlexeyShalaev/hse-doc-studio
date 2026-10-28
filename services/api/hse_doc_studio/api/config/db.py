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
    connect_timeout_s: float = Field(default=10.0, gt=0, description="Сколько ждать установки соединения с Postgres.")
    command_timeout_s: float = Field(
        default=30.0, gt=0, description="Сколько клиент ждёт ответа на команду; защита от зависшей или отрезанной базы."
    )
    pool_timeout_s: float = Field(default=10.0, gt=0, description="Сколько запрос ждёт свободное соединение из пула.")
    statement_timeout_s: float = Field(
        default=30.0, ge=0, description="statement_timeout на стороне Postgres; 0 выключает (миграции идут без лимита)."
    )
    lock_timeout_s: float = Field(
        default=10.0,
        ge=0,
        description="lock_timeout на стороне Postgres: сколько ждать чужую блокировку строки или таблицы.",
    )
    migration_lock_wait_s: float = Field(
        default=600.0, gt=0, description="Сколько ждать advisory-лок миграций, занятый другим процессом."
    )
