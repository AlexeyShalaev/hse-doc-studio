"""Токен раннера и токен задачи из заголовков запроса `/api/runner/v1`."""

from __future__ import annotations

from fastapi import Request

from hse_doc_studio.core.jobs.enums import RunnerErrorCode
from hse_doc_studio.core.jobs.errors import RunnerAuthError
from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry

JOB_TOKEN_HEADER = "X-Job-Token"  # noqa: S105 — имя заголовка, не секрет


def bearer_secret(request: Request) -> str:
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise RunnerAuthError(RunnerErrorCode.runner_unauthorized)
    return value.strip()


async def authenticated_runner(request: Request) -> Runner:
    """Раннер по токену из `Authorization: Bearer`. Отозванный и неизвестный токены неотличимы."""
    registry = await request.state.dishka_container.get(RunnerRegistry)
    return await registry.authenticate(bearer_secret(request))
