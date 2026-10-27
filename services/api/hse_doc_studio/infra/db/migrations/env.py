"""Окружение alembic: async-движок, одна цепочка ревизий, одна MetaData."""

from __future__ import annotations

import asyncio

from alembic import context
from hse_doc_studio.api.config import settings
from hse_doc_studio.infra.db import orm  # noqa: F401 — регистрирует таблицы в metadata
from hse_doc_studio.infra.db.base import Base
from hse_doc_studio.infra.db.engine import async_dsn
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
target_metadata = Base.metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    dsn = config.attributes.get("dsn") or settings.db.dsn
    engine = create_async_engine(async_dsn(dsn))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(_run)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    # Приложение передаёт открытое соединение (migrator.py), CLI alembic идёт своим движком.
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
    else:
        asyncio.run(_run_async())


if context.is_offline_mode():
    raise RuntimeError("офлайн-режим alembic не поддерживается: миграции идут только по живому соединению")
run_migrations_online()
