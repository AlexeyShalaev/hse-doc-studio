"""Диспетчер задач."""

from pathlib import Path

from pydantic import BaseModel, Field, SecretStr


class JobsConfig(BaseModel):
    """Диспетчер задач (compile, office, пакет сдачи, проверка подписей)."""

    round_trip_payloads: bool = Field(
        default=False,
        description=(
            "Пропускать каждую задачу и её результат через проводной кодек (как при удалённом раннере). "
            "Для тестов: ловит живые объекты в нагрузке; в обычной работе выключено."
        ),
    )
    lease_s: float = Field(
        default=45.0,
        gt=0,
        description="Срок аренды задачи раннером: heartbeat продлевает её, без него задача возвращается.",
    )
    reaper_interval_s: float = Field(
        default=5.0, gt=0, description="Как часто сервер возвращает задачи с истёкшей арендой и проверяет таймауты."
    )
    timeout_grace_s: float = Field(
        default=15.0,
        ge=0,
        description="Сколько раннер получает на остановку задачи после таймаута, прежде чем сервер закончит её сам.",
    )
    runner_bootstrap_token: SecretStr | None = Field(
        default=None,
        description=(
            "Одноразовый токен регистрации первого раннера. api кладёт его хеш в базу при старте; после "
            "регистрации раннера уберите значение из окружения."
        ),
    )
    build_timeout_s: int | None = Field(
        default=None,
        ge=30,
        le=3600,
        description="Предел длительности сборки из окружения: заданный побеждает правку админа.",
    )
    artifact_retention_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Срок хранения результатов сборок из окружения: заданный побеждает правку админа.",
    )
    storage_dir: Path | None = Field(
        default=None,
        description="Каталог лога задач; блобы входа и выходы лежат в объектном хранилище. По умолчанию data_dir/jobs.",
    )
    max_artifact_bytes: int = Field(
        default=512 * 1024 * 1024, gt=0, description="Предел одного выхода задачи; больший отвергается при заявке."
    )
    max_log_bytes: int = Field(
        default=8 * 1024 * 1024, gt=0, description="Предел лога одной попытки; остальное отбрасывается."
    )
