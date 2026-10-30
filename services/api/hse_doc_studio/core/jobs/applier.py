"""Применение результата задачи к тому проекта и учёт применённого.

Раннер отдаёт выходы в объектное хранилище; на том проекта их кладёт api, и только после этого
запись сборки получает итог. Между этими шагами процесс может упасть, поэтому у терминальной
задачи есть метка `applied_at`: всё, что завершилось без неё, довершается при старте.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.entities import JobSpec
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.protocols import IJobHooks
from hse_doc_studio.core.jobs.queue import QueuedJob

CODE_OUTPUT_NOT_ALLOWED = "output_not_allowed"
CODE_OUTPUT_UNSAFE_PATH = "output_unsafe_path"
CODE_OUTPUT_MISSING = "output_missing"
CODE_OUTPUT_MISMATCH = "output_mismatch"
CODE_APPLY_FAILED = "apply_failed"


class ApplyError(Exception):
    """Выход нельзя положить на том: путь вне белого списка, ссылка в пути, нет или не совпал файл."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


class IJobResultApplier(Protocol):
    async def apply(self, spec: JobSpec, artifacts: Sequence[ArtifactRef]) -> None:
        """Кладёт выходы удачной задачи в папку проекта. Повторный вызов с теми же выходами безвреден.

        `ApplyError` для выхода вне белого списка вида задачи, пути через симлинк, отсутствующего
        или несовпавшего по хешу файла.
        """
        ...

    async def discard(self, spec: JobSpec) -> None:
        """Стирает принятые выходы из хранилища, когда результат применён и учтён."""
        ...


class IJobApplyLedger(Protocol):
    async def mark_applied(self, job_id: UUID) -> bool:
        """Фиксирует, что итог задачи применён; `False`, если метка уже стояла (кто-то успел раньше)."""
        ...

    async def list_unapplied(self) -> tuple[QueuedJob, ...]:
        """Терминальные задачи без метки в порядке постановки."""
        ...


class IJobHooksFactory(Protocol):
    def for_spec(self, spec: JobSpec) -> IJobHooks | None:
        """Хуки задачи, пережившей рестарт, по её спецификации с `local_root`; `None`, если у вида хуков нет."""
        ...
