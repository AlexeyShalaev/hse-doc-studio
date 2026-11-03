"""Доставка событий запуска в api: общая часть исполнителей compose и kubernetes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from hse_doc_studio.infra.update.server_updater.client import ApiUnavailableError, IApi
from hse_doc_studio.infra.update.server_updater.journal import Journal


class Reporter:
    def __init__(self, api: IApi, journal: Journal, *, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._api = api
        self._j = journal
        self._now = now

    def emit(self, phase: str, message: str, *, level: str = "info", status: str | None = None, **extra: Any) -> None:
        run = self._j.run
        if run is None:
            return
        event: dict[str, Any] = {
            "seq": self._j.next_seq(),
            "at": self._now().isoformat(),
            "phase": phase,
            "level": level,
            "message": message[:1900],
        }
        if status:
            event["status"] = status
        event.update({k: v for k, v in extra.items() if v is not None})
        self._j.update_run(phase=phase)
        self._j.push_event(run["id"], event)
        self.flush()

    def flush(self) -> None:
        """Доставляет накопленные события по порядку; на первой ошибке останавливается и повторит позже."""
        while self._j.outbox:
            item = self._j.outbox[0]
            try:
                self._api.post_event(item["run_id"], item["event"])
            except ApiUnavailableError:
                return
            self._j.pop_event()
