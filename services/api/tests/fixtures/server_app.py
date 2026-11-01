"""Настройки серверного режима для тестов: база из шаблона с миграциями.

Контейнер server-режима появится вместе с серверными провайдерами; пока фикстура даёт только
`Settings` с mode=server и DSN, чтобы срезы подключали свои провайдеры к одной точке.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.config.db import DbConfig
from hse_doc_studio.core.mode import StudioMode

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture
def server_settings(pg_migrated_engine: AsyncEngine) -> Settings:
    dsn = pg_migrated_engine.url.render_as_string(hide_password=False)
    return Settings(mode=StudioMode.server, db=DbConfig(dsn=dsn))
