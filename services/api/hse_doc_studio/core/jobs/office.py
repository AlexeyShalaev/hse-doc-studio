"""Нагрузка и результат задачи office.convert: office-файл в соседний PDF."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.jobs.base import JobPayload, JobResultData
from hse_doc_studio.core.jobs.files import ArtifactRef, ManifestFile

# Коды причин в OfficeConvertResult.reason_code.
REASON_NOT_CONVERTIBLE = "not_convertible"
REASON_CONVERTER_UNAVAILABLE = "converter_unavailable"
REASON_WRITE_FAILED = "write_failed"


class OfficeConvertReason(StrEnum):
    """Кто просит конвертацию; нужен логам и наблюдателю, на результат не влияет."""

    upload = "upload"
    save_refresh = "save_refresh"
    package = "package"


class OfficeConvertStatus(StrEnum):
    ok = "ok"
    # Конвертации нет (нет Docker, образа, сбой LibreOffice, запись не удалась): штатный исход.
    unavailable = "unavailable"


@dataclass(frozen=True)
class OfficeConvertPayload(JobPayload):
    source: ManifestFile
    # Путь PDF от корня проекта; обычно рядом с исходником.
    output_path: str
    # Образ конвертера; None означает образ деплоя по умолчанию.
    image: str | None = None
    # Резерв для диспетчера второго этапа: встроенный конвертер берёт таймаут из конфига.
    convert_timeout_s: float | None = None
    want_pages: bool = False
    reason: OfficeConvertReason = OfficeConvertReason.upload


@dataclass(frozen=True)
class OfficeConvertResult(JobResultData):
    status: OfficeConvertStatus
    output: ArtifactRef | None = None
    pages: int | None = None
    reason_code: str = ""
    detail: str = ""
