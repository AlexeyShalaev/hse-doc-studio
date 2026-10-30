"""Прокси к общим сервисам `/api/services` (серверный режим): LanguageTool с лимитами и кэшем абзацев.

Подлинность проверяет сам маршрут: раннер присылает токен задачи (`X-Job-Token`), человек входит как обычно.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qsl
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from hse_doc_studio.api.actor import require_server_mode, resolve_actor
from hse_doc_studio.api.runner_auth import JOB_TOKEN_HEADER
from hse_doc_studio.core.jobs.enums import JobState, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.runners import IRunnerRepository, JobTokenSigner
from hse_doc_studio.core.service_pool import ServiceBusyError, ServicePoolError
from hse_doc_studio.infra.services.languagetool import LanguageToolProxy, TextTooLargeError

SERVICES_API_PREFIX = "/api/services"
_MAX_BODY_BYTES = 2_000_000

router = APIRouter(prefix=SERVICES_API_PREFIX, tags=["services"], dependencies=[Depends(require_server_mode)])


async def _subject(request: Request) -> str:
    """Ключ доли: токен задачи даёт задачу, иначе вошедший пользователь (401 для анонима)."""
    token = request.headers.get(JOB_TOKEN_HEADER)
    container = request.state.dishka_container
    if token:
        now = datetime.now(UTC)
        claims = (await container.get(JobTokenSigner)).verify(token, now)
        # Подпись и срок ещё не значат, что задача идёт: токен отозванного раннера, завершённой или
        # перехваченной другой попыткой задачи не должен открывать прокси до истечения срока.
        job = await (await container.get(IJobQueue)).get(UUID(claims.job_id))
        runner = await (await container.get(IRunnerRepository)).get(claims.runner_id)
        if (
            job is None
            or job.state is not JobState.running
            or job.runner_id is None
            or job.runner_id.hex != UUID(claims.runner_id).hex
            or runner is None
            or runner.revoked_at is not None
        ):
            raise RunnerAuthError(RunnerErrorCode.job_token_invalid)
        return f"job:{claims.job_id}"
    return f"user:{(await resolve_actor(request)).id}"


def _error(status: int, code: str, detail: str, retry_after_s: int | None = None) -> JSONResponse:
    headers = {"Retry-After": str(retry_after_s)} if retry_after_s else None
    return JSONResponse(status_code=status, content={"detail": detail, "code": code}, headers=headers)


@router.post("/languagetool/v2/check")
async def check_languagetool(request: Request) -> JSONResponse:
    """Тот же формат, что у `/v2/check` самого LanguageTool (форма urlencoded), ответ его JSON."""
    subject = await _subject(request)
    raw = await request.body()
    if len(raw) > _MAX_BODY_BYTES:
        return _error(413, "payload_too_large", "Text is too large")
    form = dict(parse_qsl(raw.decode("utf-8", errors="replace"), keep_blank_values=True))
    proxy = await request.state.dishka_container.get(LanguageToolProxy)
    try:
        return JSONResponse(await proxy.check(subject, form))
    except TextTooLargeError:
        return _error(413, "payload_too_large", "Text is too large")
    except ServiceBusyError as exc:
        return _error(429, "rate_limited", "Too many requests", exc.retry_after_s)
    except ServicePoolError as exc:
        return _error(503, "service_unavailable", "LanguageTool is unavailable", exc.retry_after_s)
    except httpx.HTTPError:
        return _error(503, "service_unavailable", "LanguageTool is unavailable", 5)
