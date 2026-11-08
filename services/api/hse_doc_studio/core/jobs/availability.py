"""Доступность сборки: для каких тегов сейчас есть исполнитель.

Локально сборка идёт в Студии, ограничений нет. На сервере сборку берут раннеры: интерфейс заранее
узнаёт, какие теги (`tex`, `office`) обслуживаются, и блокирует кнопки, а постановка без исполнителя
отвечает кодом `no_runners` (раннеров нет вовсе) или `no_runner_for_tags` (нет раннера с нужным тегом).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor

NO_RUNNERS = "no_runners"
NO_RUNNER_FOR_TAGS = "no_runner_for_tags"

# Теги сборки документа (`compile_job_tags`): о них интерфейс спрашивает заранее.
BUILD_TAGS: frozenset[str] = frozenset({"tex", "office"})


def no_runner_code(*, any_runner: bool) -> str:
    return NO_RUNNER_FOR_TAGS if any_runner else NO_RUNNERS


@dataclass(frozen=True)
class BuildAvailability:
    """`cloud`: сборка идёт на раннерах; `any_runner`: есть хоть один живой раннер; `tags`: обслуживаемые теги.

    `reasons`: для необслуживаемого тега сборки, почему (`RunnerGapReason`: личный раннер на паузе, не в сети,
    раннера с тегом нет); интерфейс называет причину, а не только «нет раннера».
    """

    cloud: bool
    any_runner: bool
    tags: frozenset[str]
    reasons: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def local(cls) -> BuildAvailability:
        return cls(cloud=False, any_runner=True, tags=BUILD_TAGS)

    def serves(self, tags: Iterable[str]) -> bool:
        return not self.cloud or frozenset(tags) <= self.tags


class IBuildAvailability(Protocol):
    async def of(self, project_id: UUID, actor: Actor) -> BuildAvailability:
        """Доступность сборки проекта для этого актора (свои личные раннеры владельца тоже в счёт)."""
        ...

    async def general(self) -> BuildAvailability:
        """Без проекта (онбординг, главная): есть ли на установке живые общие раннеры."""
        ...
