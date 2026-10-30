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


class PlacementState(StrEnum):
    waiting_personal = "waiting_personal"
    personal = "personal"
    shared = "shared"


class PlacementOwner(StrEnum):
    # Раннер того, кто смотрит, или владельца проекта.
    me = "me"
    owner = "owner"


class PlacementFallback(StrEnum):
    offline = "offline"
    busy = "busy"
    timeout = "timeout"
    lost = "lost"
    disabled = "disabled"


@dataclass(frozen=True)
class CompilePlacementInfo:
    """Где идёт сборка для этого зрителя; о раннере владельца соавтор знает только имя."""

    state: PlacementState
    runner_name: str | None = None
    runner_owner: PlacementOwner | None = None
    fallback: PlacementFallback | None = None
    wait_s: int | None = None


class ICompileWaitReader(Protocol):
    @property
    def enabled(self) -> bool:
        """Есть ли у режима очередь, о которой стоит спрашивать; поток сборки без неё не опрашивает."""
        ...

    async def of(self, compile_id: UUID) -> CompileWaitInfo | None:
        """Причина ожидания сборки; None, когда она идёт, закончена или очереди нет (локальный режим)."""
        ...

    async def placement_of(self, compile_id: UUID, viewer_id: str | None) -> CompilePlacementInfo | None:
        """Где идёт сборка; None в локальном режиме и у сборок без записи очереди."""
        ...


class NoCompileWait:
    """Локальный режим: сборка стартует сразу, ждать нечего."""

    enabled = False

    async def of(self, compile_id: UUID) -> CompileWaitInfo | None:  # noqa: ARG002
        return None

    async def placement_of(self, compile_id: UUID, viewer_id: str | None) -> CompilePlacementInfo | None:  # noqa: ARG002
        return None
