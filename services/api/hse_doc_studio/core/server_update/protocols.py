from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.core.server_update.entities import ReleaseInfo, RunEvent, RunStatus, UpdateRun


@dataclass(frozen=True)
class FeedAnswer:
    """Ответ фида релизов: `checked` ложно, если спросить не удалось (причина в `reason`)."""

    releases: tuple[ReleaseInfo, ...] = ()
    checked: bool = False
    reason: str = ""


class IReleaseSource(Protocol):
    async def fetch(self) -> FeedAnswer: ...


class IUpdateRunRepository(Protocol):
    async def add(self, run: UpdateRun) -> bool:
        """False, если уже есть активный запуск: уникальный частичный индекс делает проверку атомарной."""
        ...

    async def get(self, run_id: str) -> UpdateRun | None: ...
    async def lock(self, run_id: str) -> UpdateRun | None:
        """Строка под `FOR UPDATE` до конца транзакции: два события одного запуска не перетрут друг друга."""
        ...

    async def save(self, run: UpdateRun) -> None: ...
    async def active(self) -> UpdateRun | None: ...
    async def claim_next(self, *, now_iso: str) -> UpdateRun | None:
        """Атомарно переводит старейший `queued` в `running` и возвращает его."""
        ...

    async def page(self, window: Window) -> Found[UpdateRun]: ...
    async def last_finished(self) -> UpdateRun | None: ...
    async def last_succeeded_update(self) -> UpdateRun | None: ...
    async def failed_targets(self) -> frozenset[str]:
        """Версии, на которых обновление откатывалось или падало (планировщик не повторяет их сам)."""
        ...

    async def known_revisions(self) -> dict[str, str]:
        """Версия -> ревизия базы, на которой она работала, по истории запусков (позднее вытесняет раннее)."""
        ...

    async def counts(self) -> dict[RunStatus, int]: ...
    async def recent(self, limit: int) -> Sequence[UpdateRun]: ...


def append_events(run: UpdateRun, events: Sequence[RunEvent], *, cap: int = 300) -> UpdateRun:
    """Новые события в конец журнала запуска; старейшие вытесняются сверх `cap`."""
    merged = (*run.events, *events)[-cap:]
    return run.with_(events=merged, last_seq=max([run.last_seq, *(e.seq for e in events)]))
