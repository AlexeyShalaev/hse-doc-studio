from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from dishka import make_async_container
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.routers import services_api
from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.routing import RunnerScope
from hse_doc_studio.core.jobs.runners import IRunnerRepository, JobTokenSigner
from hse_doc_studio.infra.services.languagetool import (
    LanguageToolProxy,
    PooledLanguageCheckService,
    RemoteLanguageCheckService,
    TextTooLargeError,
    split_paragraphs,
)
from hse_doc_studio.infra.services.pool import PoolLimits, ServicePool

_TEXT = "Первый абзац.\n\nВторой абзац.\n"
_JOB_ID = UUID("00000000-0000-0000-0000-0000000000a1")
_RUNNER_ID = UUID("00000000-0000-0000-0000-0000000000b1")


def _replica(calls: list[str], status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/languages":
            return httpx.Response(200, json=[])
        text = dict(p.split("=", 1) for p in request.content.decode().split("&"))["text"]
        from urllib.parse import unquote_plus

        body = unquote_plus(text)
        calls.append(body)
        if status != 200:
            return httpx.Response(status, text="no")
        matches = [
            {"offset": m.start(), "length": 5, "message": "m", "rule": {"id": "R"}} for m in re.finditer("абзац", body)
        ]
        return httpx.Response(200, json={"language": {"code": "ru"}, "matches": matches})

    return handler


def _proxy(handler: Callable[[httpx.Request], httpx.Response], **limits: float) -> LanguageToolProxy:
    pool = ServicePool("lt", ["http://lt1"], PoolLimits(**limits))  # type: ignore[arg-type]
    return LanguageToolProxy(pool, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.unit
def test__split_paragraphs__is_lossless() -> None:
    parts = split_paragraphs(_TEXT)
    assert "".join(parts) == _TEXT
    assert len(parts) == 2


@pytest.mark.unit
async def test__proxy__cache_hit_skips_replica_and_offsets_are_global() -> None:
    calls: list[str] = []
    proxy = _proxy(_replica(calls))
    first = await proxy.check("u", {"text": _TEXT, "language": "ru"})
    second = await proxy.check("u", {"text": _TEXT, "language": "ru"})
    assert len(calls) == 1
    assert first == second
    offsets = sorted(m["offset"] for m in first["matches"])
    assert offsets[0] == _TEXT.index("абзац")
    assert offsets[1] == _TEXT.index("абзац", offsets[0] + 1)


@pytest.mark.unit
async def test__proxy__only_changed_paragraph_is_sent() -> None:
    calls: list[str] = []
    proxy = _proxy(_replica(calls))
    await proxy.check("u", {"text": _TEXT, "language": "ru"})
    await proxy.check("u", {"text": _TEXT.replace("Второй", "Третий"), "language": "ru"})
    assert calls[1] == "\nТретий абзац.\n"


@pytest.mark.unit
async def test__proxy__language_is_part_of_the_cache_key() -> None:
    calls: list[str] = []
    proxy = _proxy(_replica(calls))
    await proxy.check("u", {"text": "Один абзац.", "language": "ru"})
    await proxy.check("u", {"text": "Один абзац.", "language": "auto"})
    assert len(calls) == 2


@pytest.mark.unit
async def test__proxy__too_large_text() -> None:
    pool = ServicePool("lt", ["http://lt1"])
    proxy = LanguageToolProxy(pool, httpx.AsyncClient(), max_text_chars=5)
    with pytest.raises(TextTooLargeError):
        await proxy.check("u", {"text": "123456"})


@pytest.mark.unit
async def test__pooled_service__ensure_running_probes_replicas() -> None:
    proxy = _proxy(_replica([]))
    service = PooledLanguageCheckService(proxy._pool, proxy.probe)  # noqa: SLF001
    assert await service.ensure_running("image") == "http://lt1"
    assert service.current_base_url == "http://lt1"
    assert service.auth_headers() == {}


@pytest.mark.unit
def test__remote_service__sends_job_token_headers() -> None:
    service = RemoteLanguageCheckService("http://api/api/services/languagetool/", lambda: {"X-Job-Token": "t"})
    assert service.current_base_url == "http://api/api/services/languagetool"
    assert service.auth_headers() == {"X-Job-Token": "t"}


# ── маршрут ────────────────────────────────────────────────────────────────


async def _running_job(_job_id: object) -> object:
    return SimpleNamespace(state=JobState.running, kind=JobKind.compile, runner_id=_RUNNER_ID)


async def _live_runner(_runner_id: str) -> object:
    return SimpleNamespace(revoked_at=None, scope=RunnerScope.shared)


_RUNNING_JOB = SimpleNamespace(get=_running_job)
_LIVE_RUNNER = SimpleNamespace(get=_live_runner)


def _client(proxy: LanguageToolProxy, signer: JobTokenSigner) -> TestClient:
    from dishka import Provider, Scope, provide

    class _P(Provider):
        scope = Scope.APP

        @provide
        def proxy_(self) -> LanguageToolProxy:
            return proxy

        @provide
        def signer_(self) -> JobTokenSigner:
            return signer

        @provide
        def queue_(self) -> IJobQueue:
            return _RUNNING_JOB  # type: ignore[return-value]

        @provide
        def runners_(self) -> IRunnerRepository:
            return _LIVE_RUNNER  # type: ignore[return-value]

    container = make_async_container(_P())
    app = FastAPI()
    app.include_router(services_api.router)
    app.dependency_overrides[require_server_mode] = lambda: None

    @app.middleware("http")
    async def _attach(request, call_next):  # type: ignore[no-untyped-def]
        request.state.dishka_container = container
        return await call_next(request)

    return TestClient(app)


def _token(signer: JobTokenSigner, *, ttl: int = 60) -> str:
    return signer.sign(str(_JOB_ID), str(_RUNNER_ID), datetime.now(UTC) + timedelta(seconds=ttl))


@pytest.mark.unit
def test__route__checks_with_job_token_and_caches() -> None:
    calls: list[str] = []
    signer = JobTokenSigner([b"k" * 32])
    client = _client(_proxy(_replica(calls)), signer)
    headers = {"X-Job-Token": _token(signer)}
    for _ in range(2):
        r = client.post(
            "/api/services/languagetool/v2/check", data={"text": "Один абзац.", "language": "ru"}, headers=headers
        )
        assert r.status_code == 200
        assert r.json()["matches"]
    assert len(calls) == 1


@pytest.mark.unit
def test__route__rate_limit_returns_429_with_retry_after() -> None:
    signer = JobTokenSigner([b"k" * 32])
    client = _client(_proxy(_replica([]), user_burst=1, user_rate_per_s=0.5), signer)
    headers = {"X-Job-Token": _token(signer)}
    ok = client.post("/api/services/languagetool/v2/check", data={"text": "a"}, headers=headers)
    limited = client.post("/api/services/languagetool/v2/check", data={"text": "b"}, headers=headers)
    assert ok.status_code == 200
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert limited.headers["Retry-After"] == "2"


@pytest.mark.unit
def test__route__no_healthy_replica_is_503() -> None:
    signer = JobTokenSigner([b"k" * 32])
    client = _client(_proxy(_replica([], status=500), circuit_failures=1), signer)
    headers = {"X-Job-Token": _token(signer)}
    first = client.post("/api/services/languagetool/v2/check", data={"text": "a"}, headers=headers)
    second = client.post("/api/services/languagetool/v2/check", data={"text": "b"}, headers=headers)
    assert first.status_code == 503
    assert second.status_code == 503
    assert second.json()["code"] == "service_unavailable"
