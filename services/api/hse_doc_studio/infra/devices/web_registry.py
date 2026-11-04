"""Веб-сессии проектов в памяти процесса (docs/design/connected-devices.md, 15).

Запись и чтение это словарь: в БД и в журнал аудита сигнал не попадает. Память ограничена тремя пределами
(вкладок на человека, сессий на проект, всего на реплику); при переполнении уходят самые давние сессии. Просроченные
сессии вычищаются при записи в тот же проект и общим проходом не чаще раза в минуту.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from hse_doc_studio.core.devices.people import (
    MAX_SESSIONS_PER_PROJECT,
    MAX_SESSIONS_PER_USER,
    MAX_SESSIONS_TOTAL,
    WebSession,
    WebSignal,
)

_SWEEP_EVERY = timedelta(seconds=60)


class WebPresenceRegistry:
    def __init__(self) -> None:
        self._projects: dict[UUID, dict[tuple[str, str], WebSession]] = {}
        self._swept_at: datetime | None = None
        self._count = 0

    def observe(
        self, project_id: UUID, user_id: str, name: str, signal: WebSignal, now: datetime, window_s: int
    ) -> None:
        sessions = self._projects.setdefault(project_id, {})
        key = (user_id, signal.session_id)
        if key not in sessions:
            self._count += 1
        sessions[key] = WebSession(user_id, name, signal.session_id, signal.activity, signal.doc_id, now)
        self._expire(project_id, now, window_s)
        self._cap(project_id, user_id)
        self._sweep(now, window_s)

    def leave(self, project_id: UUID, user_id: str, session_id: str) -> None:
        sessions = self._projects.get(project_id)
        if sessions is not None and sessions.pop((user_id, session_id), None) is not None:
            self._count -= 1
            if not sessions:
                del self._projects[project_id]

    def sessions(self, project_id: UUID, now: datetime, window_s: int) -> list[WebSession]:
        horizon = now - timedelta(seconds=window_s)
        return [s for s in self._projects.get(project_id, {}).values() if s.seen_at >= horizon]

    def size(self) -> int:
        return self._count

    def _drop(self, project_id: UUID, keys: list[tuple[str, str]]) -> None:
        sessions = self._projects.get(project_id)
        if sessions is None:
            return
        for key in keys:
            if sessions.pop(key, None) is not None:
                self._count -= 1
        if not sessions:
            del self._projects[project_id]

    def _expire(self, project_id: UUID, now: datetime, window_s: int) -> None:
        horizon = now - timedelta(seconds=window_s)
        self._drop(project_id, [k for k, s in self._projects.get(project_id, {}).items() if s.seen_at < horizon])

    def _cap(self, project_id: UUID, user_id: str) -> None:
        sessions = self._projects.get(project_id, {})
        mine = sorted((s for s in sessions.values() if s.user_id == user_id), key=lambda s: s.seen_at)
        self._drop(project_id, [(s.user_id, s.session_id) for s in mine[: max(0, len(mine) - MAX_SESSIONS_PER_USER)]])
        if len(sessions) > MAX_SESSIONS_PER_PROJECT:
            oldest = sorted(sessions.values(), key=lambda s: s.seen_at)
            excess = oldest[: len(sessions) - MAX_SESSIONS_PER_PROJECT]
            self._drop(project_id, [(s.user_id, s.session_id) for s in excess])
        if self._count > MAX_SESSIONS_TOTAL:
            self._trim_total()

    def _trim_total(self) -> None:
        everything = sorted(
            ((pid, s) for pid, ss in self._projects.items() for s in ss.values()), key=lambda item: item[1].seen_at
        )
        for pid, s in everything[: self._count - MAX_SESSIONS_TOTAL]:
            self._drop(pid, [(s.user_id, s.session_id)])

    def _sweep(self, now: datetime, window_s: int) -> None:
        if self._swept_at is not None and now - self._swept_at < _SWEEP_EVERY:
            return
        self._swept_at = now
        for project_id in list(self._projects):
            self._expire(project_id, now, window_s)
