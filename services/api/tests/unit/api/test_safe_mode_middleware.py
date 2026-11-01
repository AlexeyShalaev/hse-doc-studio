"""Безопасный режим: при критической нехватке места крупные записи отклоняются 507, всё остальное идёт."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from hse_doc_studio.api.safe_mode import StorageSafeModeMiddleware
from hse_doc_studio.core.lifecycle.disk import SAFE_MODE_MAX_BODY_BYTES, SafeMode
from httpx import ASGITransport, AsyncClient


def _app(mode: SafeMode) -> FastAPI:
    app = FastAPI()

    @app.api_route("/api/v1/x", methods=["GET", "POST", "PUT"])
    async def x(request: Request) -> dict[str, int]:
        return {"n": len(await request.body())}

    @app.post("/api/admin/y")
    async def y() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/runner/z")
    async def z() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(StorageSafeModeMiddleware, safe_mode=mode)
    return app


@pytest.fixture
def mode() -> SafeMode:
    return SafeMode()


async def _client(mode: SafeMode) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=_app(mode)), base_url="http://t")


async def test__inactive__everything_passes(mode: SafeMode) -> None:
    async with await _client(mode) as c:
        r = await c.post("/api/v1/x", content=b"a" * (SAFE_MODE_MAX_BODY_BYTES + 1))

    assert r.status_code == 200


async def test__active__large_write_refused_with_code(mode: SafeMode) -> None:
    mode.set(True, "data")
    async with await _client(mode) as c:
        r = await c.put(
            "/api/v1/x", content=b"a" * (SAFE_MODE_MAX_BODY_BYTES + 1), headers={"X-Interface-Language": "en"}
        )

    assert r.status_code == 507
    assert r.json()["code"] == "storage_critical"
    assert "disk space" in r.json()["detail"]


async def test__active__small_write_reads_admin_and_runner_pass(mode: SafeMode) -> None:
    mode.set(True, "data")
    async with await _client(mode) as c:
        small = await c.post("/api/v1/x", content=b"a" * 1000)
        read = await c.get("/api/v1/x")
        admin = await c.post("/api/admin/y", content=b"a" * (SAFE_MODE_MAX_BODY_BYTES + 1))
        runner = await c.post("/api/runner/z", content=b"a" * (SAFE_MODE_MAX_BODY_BYTES + 1))

    assert [small.status_code, read.status_code, admin.status_code, runner.status_code] == [200, 200, 200, 200]


async def test__active__chunked_upload_without_length__refused(mode: SafeMode) -> None:
    mode.set(True, "data")

    async def body():  # type: ignore[no-untyped-def]
        yield b"abc"

    async with await _client(mode) as c:
        r = await c.post("/api/v1/x", content=body())

    assert r.status_code == 507


async def test__recovery__passes_again(mode: SafeMode) -> None:
    mode.set(True, "data")
    async with await _client(mode) as c:
        first = await c.post("/api/v1/x", content=b"a" * (SAFE_MODE_MAX_BODY_BYTES + 1))
        mode.set(False)
        second = await c.post("/api/v1/x", content=b"a" * (SAFE_MODE_MAX_BODY_BYTES + 1))

    assert (first.status_code, second.status_code) == (507, 200)
