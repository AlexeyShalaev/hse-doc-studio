"""Порты сборки TeX внутри infra: где идёт latexmk (docker или под kubernetes) и готово ли для этого окружение."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from hse_doc_studio.core.jobs.protocols import ProcessHandle

if TYPE_CHECKING:
    from hse_doc_studio.infra.compile.docker_image_manager import DockerStatus, ImageInfo


class ITexBuildExecutor(Protocol):
    """Одна сборка документа: поток строк лога и сентинелов из `latexmk.py`, PDF кладётся к исходнику."""

    async def run(  # noqa: PLR0913
        self,
        project_folder: Path,
        source_file: str,
        engine: str,
        max_iterations: int,
        doc_id: str,
        compile_id: uuid.UUID,
        image: str | None = None,
        on_process_started: Callable[[ProcessHandle], None] | None = None,
        project_id: uuid.UUID | None = None,
    ) -> AsyncGenerator[str, None]: ...


class IBuildEnvironment(Protocol):
    """Проверка перед сборкой: исполнитель доступен и образ на месте."""

    async def docker_status(self) -> DockerStatus: ...

    async def inspect(self, image: str) -> ImageInfo | None: ...


@dataclass(frozen=True)
class BuildBackend:
    """Исполнитель сборки раннера целиком: сборка, проверка окружения, уборка сирот прошлого запуска и тег `tex`."""

    executor: ITexBuildExecutor
    environment: IBuildEnvironment
    sweep: Callable[[], Awaitable[int]]
    tex_available: bool
    name: str
