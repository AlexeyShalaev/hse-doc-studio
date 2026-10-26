from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity, EngineType, Lang
from hse_doc_studio.core.jobs.base import JobPayload, JobResultData
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError, JobFailedError
from hse_doc_studio.core.jobs.pack import ArchiveFormat, PackSubmissionPayload
from hse_doc_studio.core.office import CONVERTIBLE_OFFICE_EXTS
from hse_doc_studio.core.value_objects import CheckResult


@dataclass(frozen=True)
class CheckPlan:
    """Какие проверки гонять после сборки; решается при постановке, а не в раннере."""

    rules_with_severity: tuple[tuple[CheckRule, CheckSeverity], ...]
    ignored_rule_ids: frozenset[str]
    needs_languagetool: bool


@dataclass(frozen=True)
class CompileJobPayload(JobPayload):
    doc_id: str
    def_id: str
    # Путь исходника от корня проекта.
    source_file: str
    engine: EngineType
    base_dir: str
    needs_compile: bool
    custom_mode: bool
    # Значение latex_passes из шаблона; раннер читает настройку пользователя в начале задачи.
    default_passes: int
    check_plan: CheckPlan


@dataclass(frozen=True)
class BuildOutcome:
    """Итог фазы сборки; `finished_at` снят до проверок и не сдвигается на их время."""

    success: bool
    status: JobStatus
    finished_at: datetime
    pages: int | None = None
    words: int | None = None
    chars: int | None = None


@dataclass(frozen=True)
class CompileResult(JobResultData):
    build_ok: bool
    check_results: tuple[CheckResult, ...] = ()
    # Поля фазы сборки (BuildOutcome): хуки по ним пишут итоговую запись.
    pages: int | None = None
    words: int | None = None
    chars: int | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True)
class JobSpec:
    """Описание задачи. Проводной конверт это все поля, кроме `local_root`.

    `local_root` (папка проекта) нужен только встроенному раннеру: в конверт он
    не попадает, а удалённый раннер получает вместо него свою рабочую папку.
    """

    id: UUID
    kind: JobKind
    tags: frozenset[str]
    project_id: UUID
    actor: Actor
    locale: Lang
    payload: JobPayload
    local_root: Path | None = None


@dataclass(frozen=True)
class JobResult:
    status: JobStatus
    data: JobResultData | None = None
    error: JobError | None = None

    def data_as[D: JobResultData](self, cls: type[D]) -> D:
        if not isinstance(self.data, cls):
            raise JobFailedError(f"job result has no {cls.__name__} data")
        return self.data

    def raise_for_error(self) -> None:
        if self.error is not None:
            self.error.raise_for_error()


def compile_payload_of(spec: JobSpec) -> CompileJobPayload:
    """Нагрузка compile-задачи; другой вид или тип нагрузки это ошибка программиста."""
    if spec.kind is not JobKind.compile or not isinstance(spec.payload, CompileJobPayload):
        raise TypeError(f"not a compile job: {spec.kind}")
    return spec.payload


def compile_job_tags(needs_compile: bool, source_ext: str) -> frozenset[str]:
    """`tex` для latexmk, `office` для копирования office-файла с превью, иначе без тегов."""
    if needs_compile:
        return frozenset({"tex"})
    if source_ext.lower() in CONVERTIBLE_OFFICE_EXTS:
        return frozenset({"office"})
    return frozenset()


def pack_job_tags(archive_format: ArchiveFormat) -> frozenset[str]:
    """`pack` и, для 7z и rar, тег внешней утилиты: раннер без неё такую задачу не возьмёт."""
    if archive_format in (ArchiveFormat.sevenz, ArchiveFormat.rar):
        return frozenset({"pack", f"archive:{archive_format.value}"})
    return frozenset({"pack"})


def job_tags(kind: JobKind, payload: JobPayload) -> frozenset[str]:
    if kind is JobKind.compile and isinstance(payload, CompileJobPayload):
        return compile_job_tags(payload.needs_compile, Path(payload.source_file).suffix)
    if kind is JobKind.office_convert:
        return frozenset({"office"})
    if kind is JobKind.pack_submission and isinstance(payload, PackSubmissionPayload):
        return pack_job_tags(payload.archive_format)
    raise ValueError(f"no tags for job kind {kind}")
