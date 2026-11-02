"""Выбор pg_dump и pg_restore под версию сервера: клиент новее сервера пишет в дамп неизвестные ему настройки."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

PG_LIB = Path("/usr/lib/postgresql")
DEFAULT_NAMES = {"pg_dump", "pg_restore", "psql"}


async def server_major(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text("SHOW server_version_num"))).scalar_one()) // 10000


def resolve_binary(configured: str, major: int | None, *, lib: Path = PG_LIB) -> str:
    """Свой путь из настроек берётся как есть; имя по умолчанию заменяется клиентом той же версии, если он есть."""
    if configured not in DEFAULT_NAMES or major is None:
        return configured
    candidate = lib / str(major) / "bin" / configured
    return str(candidate) if candidate.exists() else configured
