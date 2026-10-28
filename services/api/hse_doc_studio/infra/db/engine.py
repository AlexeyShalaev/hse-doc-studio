"""Создание async-движка Postgres."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from hse_doc_studio.api.config.db import DbConfig
from hse_doc_studio.infra.db.errors import DbConfigError

_ASYNC_DRIVER = "postgresql+asyncpg"


def async_dsn(dsn: str | None) -> str:
    """DSN с драйвером asyncpg: ``postgresql://`` и ``postgres://`` дополняются, чужой драйвер отвергается."""
    if not dsn or not dsn.strip():
        raise DbConfigError("HSE_STUDIO__DB__DSN не задан")
    try:
        url = make_url(dsn.strip())
    except Exception as exc:
        raise DbConfigError("HSE_STUDIO__DB__DSN не разобрать как URL") from exc
    backend, _, driver = url.drivername.partition("+")
    if backend not in ("postgresql", "postgres") or driver not in ("", "asyncpg"):
        raise DbConfigError(f"поддерживается только Postgres через asyncpg, получено {url.drivername}")
    return url.set(drivername=_ASYNC_DRIVER).render_as_string(hide_password=False)


def connect_args(cfg: DbConfig) -> dict[str, Any]:
    """Таймауты asyncpg и сервера: без них зависшая или отрезанная база держит запросы и пул бесконечно.

    ``idle_in_transaction_session_timeout`` не ставим: лидерский advisory-лок живёт на соединении с открытой
    транзакцией, и сервер сбросил бы его вместе с лидерством.
    """
    server_settings = {
        "statement_timeout": str(int(cfg.statement_timeout_s * 1000)),
        "lock_timeout": str(int(cfg.lock_timeout_s * 1000)),
    }
    return {
        "timeout": cfg.connect_timeout_s,
        "command_timeout": cfg.command_timeout_s,
        "server_settings": server_settings,
    }


def create_engine(cfg: DbConfig) -> AsyncEngine:
    return create_async_engine(
        async_dsn(cfg.dsn),
        pool_size=cfg.pool_size,
        max_overflow=cfg.max_overflow,
        pool_timeout=cfg.pool_timeout_s,
        pool_pre_ping=True,
        connect_args=connect_args(cfg),
        echo=cfg.echo,
        # Значения параметров (e-mail в ключах входа, хеши) не должны попадать в текст ошибок и логи.
        hide_parameters=True,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: репозиторий отдаёт доменные сущности, а не живые ORM-объекты
    return async_sessionmaker(engine, expire_on_commit=False)
