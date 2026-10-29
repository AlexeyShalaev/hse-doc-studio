"""Приём выходов задач: раннер льёт файлы по подписанному PUT, сервер проверяет и не доверяет раннеру."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from hse_doc_studio.core.jobs.files import ArtifactRef
from hse_doc_studio.core.storage.errors import ObjectStoreError
from hse_doc_studio.core.storage.models import PresignedUrl
from hse_doc_studio.core.storage.ports import ObjectSource

_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA256_LEN = 64


class OutputRejectedError(ObjectStoreError):
    """Выход отвергнут: чужой префикс, превышен предел, нет объекта, не совпали размер или sha256."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OutputLimits:
    max_file_bytes: int = 256 * 1024**2
    max_total_bytes: int = 1024**3
    max_files: int = 1000


@dataclass(frozen=True)
class OutputSpec:
    """Заявка раннера: файл относительно рабочей папки, его размер и sha256."""

    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class OutputUpload:
    """Куда лить файл: `url` None означает, что хранилище ссылок не выдаёт и файл принимает `IJobOutputIngest.put`."""

    path: str
    key: str
    url: PresignedUrl | None


def output_prefix(project_id: str, job_id: str) -> str:
    """Префикс выходов задачи; идентификаторы обязаны быть одним безопасным сегментом."""
    for value in (project_id, job_id):
        if not _SEGMENT_RE.fullmatch(value) or ".." in value:
            msg = "идентификатор проекта или задачи не годится для ключа"
            raise OutputRejectedError("invalid_identifier", msg)
    return f"artifacts/{project_id}/jobs/{job_id}/"


class IJobOutputIngest(Protocol):
    """Все вызовы привязаны к паре (project_id, job_id), которую API берёт из токена задачи, а не из тела запроса."""

    async def begin(
        self,
        project_id: str,
        job_id: str,
        outputs: Sequence[OutputSpec],
        *,
        limits: OutputLimits | None = None,
        expires_in_s: int = 900,
    ) -> list[OutputUpload]:
        """Проверяет заявку и выдаёт ссылки на ключи только своей задачи."""
        ...

    async def put(self, project_id: str, job_id: str, spec: OutputSpec, source: ObjectSource) -> ArtifactRef:
        """Приём через api, когда ссылок нет: проверка та же, что и в commit."""
        ...

    async def commit(
        self,
        project_id: str,
        job_id: str,
        outputs: Sequence[OutputSpec],
        *,
        limits: OutputLimits | None = None,
    ) -> list[ArtifactRef]:
        """Сверяет head, размер и sha256 каждого выхода; расходящийся объект удаляется и выход отвергается."""
        ...
