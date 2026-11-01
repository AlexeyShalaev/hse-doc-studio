"""Бэкапы сервера (HSE_STUDIO__BACKUPS__*). Назначения, расписание и хранение правятся в админке."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class BackupProvisionConfig(BaseModel):
    """Начальная настройка из окружения (Helm, compose): применяется на старте, только если назначений ещё нет."""

    destination_kind: Literal["none", "local", "s3"] = Field(
        default="none", description="Тип назначения по умолчанию; none отключает провижининг."
    )
    name: str = Field(default="default", description="Имя назначения.")
    local_path: str = Field(default="main", description="Подкаталог корня локальных назначений (kind=local).")
    endpoint: str | None = Field(default=None, description="Адрес S3 (пусто значит AWS).")
    region: str = Field(default="us-east-1", description="Регион S3.")
    bucket: str | None = Field(default=None, description="Бакет S3.")
    prefix: str = Field(default="", description="Префикс бэкапов в бакете.")
    path_style: bool = Field(default=True, description="Адресация bucket в пути (MinIO, Ceph).")
    access_key: SecretStr | None = Field(default=None, description="Ключ доступа S3.")
    secret_key: SecretStr | None = Field(default=None, description="Секретный ключ S3.")
    schedule_enabled: bool = Field(default=True, description="Включить расписание.")
    schedule_kind: Literal["interval", "cron"] = Field(default="interval", description="Вид расписания.")
    interval_hours: int = Field(default=24, ge=1, le=2160, description="Интервал в часах (schedule_kind=interval).")
    cron: str = Field(default="0 3 * * *", description="Cron из пяти полей, UTC (schedule_kind=cron).")
    keep_last: int = Field(default=7, ge=0, description="Хранить последних N бэкапов (0 отключает правило).")
    keep_days: int = Field(default=30, ge=0, description="Хранить дней (0 отключает правило).")
    encryption_mode: Literal["installation", "passphrase"] = Field(
        default="installation", description="Ключ шифрования: ключ установки или парольная фраза."
    )
    passphrase: SecretStr | None = Field(default=None, description="Парольная фраза (от 12 символов).")
    notify_admins: bool = Field(default=True, description="Уведомлять администраторов о сбое бэкапа.")


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
    restore_from_admin: bool = Field(
        default=True,
        description="Разрешает восстановление из админки (режим обслуживания). false оставляет только предпросмотр.",
    )
    restart_after_restore: bool = Field(
        default=True,
        description="После восстановления из админки процесс api завершается, и супервизор (compose, Kubernetes) "
        "поднимает его заново. false оставляет api в режиме обслуживания до ручного перезапуска.",
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
    provision: BackupProvisionConfig = Field(default_factory=BackupProvisionConfig)
