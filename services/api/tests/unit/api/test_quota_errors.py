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
