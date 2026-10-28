"""Диспетчер задач."""

from pydantic import BaseModel, Field


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
