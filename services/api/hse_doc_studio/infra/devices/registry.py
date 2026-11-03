"""Присутствие в памяти процесса: свежее время сигнала и то, что уже записано в БД.

Сигнал приходит раз в минуту, и писать в БД каждый тик незачем: запись идёт, когда состояние изменилось или
прошёл `persist_interval_s`. Читающие запросы накладывают время из памяти на запись БД, поэтому «онлайн» точен на
той реплике, куда пришёл сигнал, а на соседней отстаёт не больше интервала записи (он заметно короче окна «онлайн»).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from hse_doc_studio.core.devices.entities import DeviceReport


@dataclass
class _Seen:
    at: datetime
    persisted_at: datetime | None
    digest: str


def _digest(report: DeviceReport) -> str:
    """Отпечаток отчёта без того, что меняется каждый тик (время последней синхронизации входит: оно редкое)."""
    raw = json.dumps(_plain(report), sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()  # noqa: S324 — отпечаток, не защита


def _plain(report: DeviceReport) -> object:
    from dataclasses import asdict  # noqa: PLC0415

    return asdict(report)


class PresenceRegistry:
    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], _Seen] = {}

    def observe(self, user_id: str, report: DeviceReport, now: datetime, persist_interval_s: int) -> bool:
        """Запоминает сигнал; True, если его нужно записать в БД сейчас."""
        key = (user_id, report.device_id)
        digest = _digest(report)
        previous = self._seen.get(key)
        due = (
            previous is None
            or previous.persisted_at is None
            or previous.digest != digest
            or (now - previous.persisted_at).total_seconds() >= persist_interval_s
        )
        self._seen[key] = _Seen(
            at=now, persisted_at=now if due else previous.persisted_at if previous else None, digest=digest
        )
        return due

    def last_seen(self, user_id: str, device_id: str) -> datetime | None:
        seen = self._seen.get((user_id, device_id))
        return seen.at if seen is not None else None

    def forget(self, user_id: str, device_id: str) -> None:
        self._seen.pop((user_id, device_id), None)

    def prune(self, horizon: datetime) -> None:
        for key in [k for k, v in self._seen.items() if v.at < horizon]:
            del self._seen[key]
