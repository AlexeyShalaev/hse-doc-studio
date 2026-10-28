"""Схема OpenAPI строится целиком: `-> Response` в роутерах dishka не должно ломать её (раньше был 500)."""

from __future__ import annotations

from fastapi import FastAPI
from hse_doc_studio.api.routers.v1 import api_router


def test__openapi__all_routers__schema_builds() -> None:
    app = FastAPI()
    app.include_router(api_router)

    schema = app.openapi()

    assert "/api/v1/fonts/{filename}/file" in schema["paths"]
    assert "/api/v1/auth/register" in schema["paths"]
