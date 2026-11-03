"""Старт сервера не трогает локальные ресурсы машины, которых у сервера нет."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from tests.integration.api.personal.conftest import Stand

if TYPE_CHECKING:
    from fastapi import FastAPI

pytestmark = pytest.mark.pg


async def test__server_startup__local_ollama_sync_is_not_scheduled(stand: Stand) -> None:
    # Синк локальной Ollama пишет провайдера от имени актора; на старте сервера актора нет,
    # и задача каждый раз заканчивалась ActorRequired с трейсбеком в логе.
    app = cast("FastAPI", stand.client.app)

    assert not hasattr(app.state, "sync_ollama_provider_task")
