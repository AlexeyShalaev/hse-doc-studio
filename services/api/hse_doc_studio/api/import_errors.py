"""HTTP-вид отказа при импорте проекта: тело `{detail, code}`, статус по коду."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.core.projects.importer import ProjectImportCode, ProjectImportError

_UNPROCESSABLE = 422
_TOO_LARGE = 413
_UNAVAILABLE = 503

PROJECT_IMPORT_STATUS: Mapping[ProjectImportCode, int] = {
    ProjectImportCode.archive_invalid: _UNPROCESSABLE,
    ProjectImportCode.archive_unsafe: _UNPROCESSABLE,
    ProjectImportCode.no_project: _UNPROCESSABLE,
    ProjectImportCode.project_newer: _UNPROCESSABLE,
    ProjectImportCode.too_large: _TOO_LARGE,
    ProjectImportCode.unavailable: _UNAVAILABLE,
}


async def _handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProjectImportError)  # noqa: S101 — обработчик зарегистрирован только на этот тип
    return JSONResponse(
        status_code=PROJECT_IMPORT_STATUS[exc.code],
        content={"detail": exc.message, "code": f"import_{exc.code.value}"},
    )


def install_project_import_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProjectImportError, _handler)
