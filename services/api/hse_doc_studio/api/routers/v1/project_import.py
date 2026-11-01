"""Загрузка проекта из локальной Студии: zip с папкой проекта становится новым проектом загрузившего."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, File, UploadFile

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.session import ProjectImportResult, ProjectImportWarning
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.projects.importer import ImportLimits, ProjectImportCode, ProjectImportError
from hse_doc_studio.use_cases.projects.import_project import ImportProjectInput, ImportProjectUC

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(require_server_mode)])

_CHUNK = 1024 * 1024


async def _receive(upload: UploadFile, target: Path, max_bytes: int) -> None:
    """Складывает загрузку на диск, не давая ей перерасти предел (больший архив не влезет и распакованным)."""
    size = 0
    with target.open("wb") as out:
        while chunk := await upload.read(_CHUNK):
            size += len(chunk)
            if size > max_bytes:
                mib = max_bytes // (1024 * 1024)
                raise ProjectImportError(
                    ProjectImportCode.too_large,
                    localized_error(
                        f"Архив больше допустимого: не более {mib} МБ.", f"The archive is too large: at most {mib} MB."
                    ),
                )
            await asyncio.to_thread(out.write, chunk)


@router.post("/projects/import", response_model=ProjectImportResult, status_code=201)
async def import_project(
    uc: FromDishka[ImportProjectUC],
    limits: FromDishka[ImportLimits],
    file: UploadFile = File(...),
) -> ProjectImportResult:
    with tempfile.TemporaryDirectory(prefix="hse-import-") as scratch:
        archive = Path(scratch) / "project.zip"
        await _receive(file, archive, limits.max_unpacked_bytes)
        report = await uc.execute(ImportProjectInput(archive=archive))
    return ProjectImportResult(
        project_id=str(report.project_id),
        name=report.name,
        id_regenerated=report.id_regenerated,
        files=report.files,
        bytes=report.bytes,
        chats=report.chats,
        warnings=[ProjectImportWarning(code=w.code.value, detail=w.detail) for w in report.warnings],
    )
