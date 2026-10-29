from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from hse_doc_studio.core.jobs.entities import JobResult
from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.jobs.wire import JobEnvelope


@dataclass(frozen=True)
class OutputFile:
    """Выход задачи: заявленная ссылка и файл на диске раннера, откуда цикл прочитает байты."""

    ref: ArtifactRef
    path: Path


@dataclass(frozen=True)
class JobOutcome:
    result: JobResult
    outputs: tuple[OutputFile, ...] = ()


@dataclass(frozen=True)
class JobContext:
    """Что цикл даёт исполнителю: строка живого лога и признак отмены."""

    log: Callable[[str], None]
    cancelled: asyncio.Event


class JobExecutor(Protocol):
    """Исполнитель вида задач. Ожидаемый сбой бросает `JobFailure`; отмену цикл доставляет отменой задачи."""

    async def execute(self, envelope: JobEnvelope, ctx: JobContext) -> JobOutcome: ...
