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
