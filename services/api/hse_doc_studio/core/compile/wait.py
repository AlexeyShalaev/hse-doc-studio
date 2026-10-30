"""Почему сборка ещё не идёт: очередь, нет раннера, потеря раннера, замена более новой сборкой."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class CompileWaitReason(StrEnum):
    queued = "queued"
    quota_wait = "quota_wait"
    no_runner = "no_runner"
    runner_lost = "runner_lost"
    superseded = "superseded"
    # Сборка ждёт личный раннер владельца проекта (окно ожидания, потом общие раннеры).
    personal_runner = "personal_runner"


@dataclass(frozen=True)
class CompileWaitInfo:
    reason: CompileWaitReason
    # Место среди ожидающих, с 1.
    queue_position: int | None = None
    wait_hint_seconds: int | None = None
    # Номер текущей попытки и их максимум: для runner_lost.
    attempt: int | None = None
    max_attempts: int | None = None


class ICompileWaitReader(Protocol):
    @property
    def enabled(self) -> bool:
        """Есть ли у режима очередь, о которой стоит спрашивать; поток сборки без неё не опрашивает."""
        ...

    async def of(self, compile_id: UUID) -> CompileWaitInfo | None:
        """Причина ожидания сборки; None, когда она идёт, закончена или очереди нет (локальный режим)."""
        ...


class NoCompileWait:
    """Локальный режим: сборка стартует сразу, ждать нечего."""

    enabled = False

    async def of(self, compile_id: UUID) -> CompileWaitInfo | None:  # noqa: ARG002
        return None
