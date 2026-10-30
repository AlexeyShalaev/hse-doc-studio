from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.jobs.enums import JobPriorityClass


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
    # Класс очереди серверного диспетчера; встроенный порядок задач не меняет.
    priority_class: JobPriorityClass = JobPriorityClass.checks
    # Можно ли после потери раннера безопасно поставить задачу заново: выходы применяет только API после завершения.
    retryable: bool = False
    # Сколько попыток даёт серверная очередь (первая и повторы после потери раннера).
    max_attempts: int = 1
    # Может ли задачу вида взять личный раннер владельца проекта. Итог, несущий доверие третьим лицам
    # (проверка подписи), считают только общие раннеры: владелец мог бы подменить его на своей машине.
    personal_runner_allowed: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if not self.retryable and self.max_attempts != 1:
            raise ValueError("a non-retryable kind has exactly one attempt")
