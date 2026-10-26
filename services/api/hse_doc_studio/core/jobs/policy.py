from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobKindPolicy:
    """Как диспетчер обращается с видом задачи."""

    # Можно ли ждать результат через `run`.
    awaitable: bool = False
    # Можно ли запускать в фоне без ожидания (`submit_detached`).
    detachable: bool = False
    # Пишет ли задача живой лог в шину.
    streams_log: bool = False
    # Учитывается ли в `is_active` и `has_any_active` (самообновление, перенос проекта).
    counts_as_active: bool = False
    # Блокирует ли операции над папкой проекта, пока идёт.
    blocks_folder_ops: bool = False
    # Безопасно ли повторить задачу с теми же входами.
    idempotent: bool = False
    # Сколько задач вида встроенный диспетчер выполняет одновременно (None без лимита).
    embedded_concurrency: int | None = None
    # Таймаут по умолчанию для диспетчера второго этапа; встроенный применяет только явный.
    default_timeout_s: float | None = None
