"""Потолок тела загрузки проекта: отказ 413 до разбора формы."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from hse_doc_studio.api.body_limit import BODY_OVERHEAD_BYTES, UploadBodyLimitMiddleware

LIMIT = BODY_OVERHEAD_BYTES + 1024


def make_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(UploadBodyLimitMiddleware, path_suffix="/projects/import", max_bytes=LIMIT)

    @app.post("/api/v1/projects/import")
    async def _import(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    @app.post("/api/v1/other")
    async def _other(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    return TestClient(app)


def test__import__within_limit__passes() -> None:
    assert make_client().post("/api/v1/projects/import", content=b"x" * 100).json() == {"size": 100}


def test__import__declared_length_over_limit__413() -> None:
    response = make_client().post("/api/v1/projects/import", content=b"x" * (LIMIT + 1))

    assert response.status_code == 413
    assert response.json()["code"] == "import_too_large"


def test__import__chunked_body_over_limit__413() -> None:
    def chunks():  # type: ignore[no-untyped-def]
        for _ in range(3):
            yield b"x" * (LIMIT // 2)

    response = make_client().post("/api/v1/projects/import", content=chunks())

    assert response.status_code == 413


def test__other_route__not_limited() -> None:
    assert make_client().post("/api/v1/other", content=b"x" * (LIMIT + 1)).status_code == 200
