"""Пул реплик ONLYOFFICE Document Server для серверного режима: липкая реплика на документ и лимит сессий.

Реплики внешние (compose, Kubernetes), поэтому ни запуска, ни установки образов нет. Лимит сессий общий на
установку: Community Edition принимает около двадцати одновременных соединений, запас оставляем под
повторные подключения. Сессия занимает место при выдаче конфига и освобождается колбэком о закрытии,
сохранением с закрытием или по сроку без вестей.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from hse_doc_studio.core.service_pool import ServiceUnavailableError
from hse_doc_studio.infra.services.pool import ServicePool

logger = structlog.get_logger()


@dataclass
class _Session:
    doc_id: str | None
    expires_at: float


class PooledOfficeEditorService:
    def __init__(
        self,
        pool: ServicePool,
        jwt_secret: str,
        probe: Callable[[str], Awaitable[bool]],
        *,
        max_sessions: int = 18,
        session_ttl_s: float = 1800.0,
        probe_interval_s: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._pool = pool
        self._jwt_secret = jwt_secret
        self._probe = probe
        self._max_sessions = max_sessions
        self._ttl = session_ttl_s
        self._probe_interval = probe_interval_s
        self._clock = clock
        self._sessions: dict[str, _Session] = {}
        self._probed_at: float | None = None

    @property
    def jwt_secret(self) -> str:
        return self._jwt_secret

    @property
    def base_url(self) -> str | None:
        """Адрес любой здоровой реплики; адрес документа даёт `base_url_for`."""
        try:
            return self._pool.pick_url()
        except ServiceUnavailableError:
            return None

    @property
    def active_sessions(self) -> int:
        self._sweep()
        return len(self._sessions)

    def base_url_for(self, key: str) -> str | None:
        try:
            return self._pool.pick_sticky(key)
        except ServiceUnavailableError:
            return None

    async def is_image_missing(self, image: str | None = None) -> bool:  # noqa: ARG002 — образами управляет оператор
        return False

    async def ensure_running(self, image: str | None = None) -> str | None:  # noqa: ARG002
        """Для пула это опрос реплик (не чаще интервала); возвращает любую здоровую или None."""
        now = self._clock()
        if self._probed_at is None or now - self._probed_at >= self._probe_interval:
            self._probed_at = now
            await self._pool.probe(self._probe)
        return self.base_url

    async def apply_ai_settings(self, desired: dict[str, Any]) -> bool:  # noqa: ARG002
        """Настройки ИИ реплик задаёт оператор вместе с развёртыванием: до контейнеров пул не дотягивается."""
        return False

    def try_open_session(self, key: str, doc_id: str | None = None) -> bool:
        self._sweep()
        existing = self._sessions.get(key)
        if existing is None and len(self._sessions) >= self._max_sessions:
            logger.info("office_pool.busy", sessions=len(self._sessions), limit=self._max_sessions)
            return False
        self._sessions[key] = _Session(doc_id, self._clock() + self._ttl)
        return True

    def mark_active(self, key: str) -> None:
        """Документ уже открыт на реплике: сессию учитываем, даже если лимит исчерпан."""
        if not key:
            return
        session = self._sessions.get(key)
        if session is None:
            self._sessions[key] = _Session(None, self._clock() + self._ttl)
        else:
            session.expires_at = self._clock() + self._ttl

    def mark_closed(self, key: str) -> None:
        self._sessions.pop(key, None)

    def touch(self, doc_id: str | None = None) -> None:
        """Keepalive вкладки продлевает только её сессии."""
        if doc_id is None:
            return
        expires_at = self._clock() + self._ttl
        for session in self._sessions.values():
            if session.doc_id == doc_id:
                session.expires_at = expires_at

    def _sweep(self) -> None:
        now = self._clock()
        for key in [k for k, s in self._sessions.items() if s.expires_at <= now]:
            del self._sessions[key]


class ConfiguredReachability:
    """Адрес API глазами реплик Document Server задаёт оператор: сети развёртывания заранее известны."""

    def __init__(self, url: str) -> None:
        self._url = url.rstrip("/")

    async def base_url(self) -> str:
        return self._url
