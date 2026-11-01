"""Отказ по пределу проекта отдаётся как 413 с кодом project_quota_exceeded и числами."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hse_doc_studio.api.quota_errors import install_quota_error_handlers
from hse_doc_studio.core.projects.usage import ProjectQuotaExceededError

pytestmark = pytest.mark.unit


def test__quota_error__is_413_with_code_and_numbers() -> None:
    app = FastAPI()
    install_quota_error_handlers(app)

    @app.put("/x")
    async def _put() -> None:
        raise ProjectQuotaExceededError(uuid4(), 900, 1000, 200)

    response = TestClient(app).put("/x")

    assert response.status_code == 413
    body = response.json()
    assert (body["code"], body["used_bytes"], body["limit_bytes"]) == ("project_quota_exceeded", 900, 1000)


def test__owner_quota_error__build_limit_is_429_with_period_reset() -> None:
    from datetime import UTC, datetime

    from hse_doc_studio.core.quotas.errors import QuotaExceededError
    from hse_doc_studio.core.quotas.kinds import QuotaKind, QuotaScope

    app = FastAPI()
    install_quota_error_handlers(app)

    @app.post("/b")
    async def _post() -> None:
        raise QuotaExceededError(QuotaKind.builds, QuotaScope.user, 30, 30, datetime(2026, 12, 1, tzinfo=UTC))

    response = TestClient(app).post("/b")

    assert response.status_code == 429
    assert response.json() == {
        "detail": "Quota exceeded",
        "code": "quota_exceeded",
        "resource": "builds",
        "scope": "user",
        "used": 30,
        "limit": 30,
        "resets_at": "2026-12-01T00:00:00+00:00",
    }


def test__owner_quota_error__storage_is_413_owner_storage_exceeded() -> None:
    from hse_doc_studio.core.quotas.errors import QuotaExceededError
    from hse_doc_studio.core.quotas.kinds import QuotaKind, QuotaScope

    app = FastAPI()
    install_quota_error_handlers(app)

    @app.put("/s")
    async def _put() -> None:
        raise QuotaExceededError(QuotaKind.storage, QuotaScope.org, 900, 1000, None)

    response = TestClient(app).put("/s")

    assert (response.status_code, response.json()["code"], response.json()["resets_at"]) == (
        413,
        "owner_storage_exceeded",
        None,
    )
