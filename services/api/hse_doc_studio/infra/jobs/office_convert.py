"""Конвертация office-файла в соседний PDF: одна реализация для всех вызывающих."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path, PurePosixPath

from hse_doc_studio.core.jobs.base import JobResultData
from hse_doc_studio.core.jobs.office import (
    REASON_CONVERTER_UNAVAILABLE,
    REASON_NOT_CONVERTIBLE,
    REASON_WRITE_FAILED,
    OfficeConvertPayload,
    OfficeConvertResult,
    OfficeConvertStatus,
)
from hse_doc_studio.core.jobs.outputs import IJobOutputs
from hse_doc_studio.core.jobs.protocols import JobContext
from hse_doc_studio.core.office import CONVERTIBLE_OFFICE_EXTS, IOfficeConvertService


def _page_count(pdf_bytes: bytes) -> int | None:
    try:
        from pypdf import PdfReader  # noqa: PLC0415 — тяжёлый импорт только по месту

        return len(PdfReader(BytesIO(pdf_bytes)).pages)
    except Exception:  # noqa: BLE001 — счётчик страниц не критичен
        return None


async def convert_office_to_sibling(  # noqa: PLR0913
    converter: IOfficeConvertService,
    outputs: IJobOutputs,
    workspace: Path,
    source_path: str,
    output_path: str,
    image: str | None,
    want_pages: bool,
) -> OfficeConvertResult:
    """Конвертирует office-файл и кладёт PDF в `output_path` внутри `workspace`.

    Исключения конвертера не перехватывает: сборка сохраняет прежнюю семантику
    сбоя, а диспетчер превращает их в проваленную задачу для остальных вызывающих.
    `image=None` вызывает конвертер без аргумента образа (образ деплоя по умолчанию).
    """
    if PurePosixPath(source_path).suffix.lower() not in CONVERTIBLE_OFFICE_EXTS:
        return OfficeConvertResult(status=OfficeConvertStatus.unavailable, reason_code=REASON_NOT_CONVERTIBLE)
    source = workspace / source_path
    if image is None:
        pdf_bytes = await converter.convert_to_pdf(source)
    else:
        pdf_bytes = await converter.convert_to_pdf(source, image=image)
    if pdf_bytes is None:
        return OfficeConvertResult(status=OfficeConvertStatus.unavailable, reason_code=REASON_CONVERTER_UNAVAILABLE)
    try:
        output = await asyncio.to_thread(outputs.write_output, workspace, output_path, pdf_bytes)
    except (OSError, ValueError) as exc:
        # ValueError: путь не прошел проверку выходов (обратный слэш в имени, символьная
        # ссылка наружу). Превью best-effort: сборка и загрузка от этого не падают.
        return OfficeConvertResult(
            status=OfficeConvertStatus.unavailable, reason_code=REASON_WRITE_FAILED, detail=str(exc)
        )
    pages = await asyncio.to_thread(_page_count, pdf_bytes) if want_pages else None
    return OfficeConvertResult(status=OfficeConvertStatus.ok, output=output, pages=pages)


class OfficeConvertHandler:
    """Обработчик office.convert поверх конвертера; регистрируется слайсом первого вызывающего."""

    def __init__(self, converter: IOfficeConvertService) -> None:
        self._converter = converter

    async def handle(self, payload: OfficeConvertPayload, ctx: JobContext) -> JobResultData:
        # path_of проверяет, что исходник лежит внутри рабочей папки.
        ctx.path_of(payload.source)
        return await convert_office_to_sibling(
            self._converter,
            ctx.outputs,
            ctx.workspace,
            payload.source.path,
            payload.output_path,
            payload.image,
            payload.want_pages,
        )
