"""Бэкапы сервера (HSE_STUDIO__BACKUPS__*). Назначения, расписание и хранение правятся в админке."""

from pathlib import Path

from pydantic import BaseModel, Field


class BackupsConfig(BaseModel):
    enabled: bool = Field(
        default=True, description="Включает планировщик бэкапов и раздел админки; false убирает фоновый цикл целиком."
    )
    tick_s: float = Field(
        default=30.0,
        ge=1,
        le=3600,
        description="Как часто планировщик проверяет, не пора ли запустить бэкап по расписанию.",
    )
    local_root: Path | None = Field(
        default=None,
        description="Корень локальных назначений: каталог бэкапа это подкаталог корня. Пусто значит data_dir/backups. "
        "Для защиты от потери диска смонтируйте сюда отдельный том.",
    )
    tmp_dir: Path | None = Field(
        default=None,
        description="Где собираются зашифрованные части до загрузки (нужно места на самую большую часть). "
        "Пусто значит data_dir/tmp/backup.",
    )
    max_object_bytes: int = Field(
        default=256 * 1024**3, ge=1, description="Предел размера одной части бэкапа в назначении."
    )
    multipart_threshold_bytes: int = Field(
        default=64 * 1024**2, ge=5 * 1024**2, description="С какого размера часть уходит в S3 кусками."
    )
    pg_dump_binary: str = Field(
        default="pg_dump", description="Исполняемый файл pg_dump (версия не ниже сервера Postgres)."
    )
    pg_restore_binary: str = Field(default="pg_restore", description="Исполняемый файл pg_restore.")
    dump_timeout_s: float = Field(
        default=6 * 3600.0, gt=0, description="Сколько ждать завершения pg_dump и pg_restore."
    )
