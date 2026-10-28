"""Возможности клиента закрывают локальные операции с проектами на общем сервере."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.routers.v1 import projects as projects_router
from hse_doc_studio.api.schemas.project import CreateProjectRequest, MoveProjectRequest
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.paths import PathMapping


async def test__move__server_mode__closed_before_use_case(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    uc = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await projects_router.move_project(uuid4(), MoveProjectRequest(folder="/x"), uc, PathMapping())

    assert exc.value.status_code == 404
    uc.execute.assert_not_called()


async def test__create__local_without_folder__unprocessable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mode", StudioMode.local)
    body = CreateProjectRequest(name="n", pack_id="p", template_id="t", version="1")
    uc = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await projects_router.create_project(body, uc, PathMapping())

    assert exc.value.status_code == 422
    uc.execute.assert_not_called()
