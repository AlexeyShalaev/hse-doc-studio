"""Доступна ли сборка проекта сейчас: для каких тегов есть исполнитель."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.jobs.availability import BuildAvailability, IBuildAvailability


@dataclass(frozen=True)
class GetBuildAvailabilityInput:
    project_id: UUID


class GetBuildAvailabilityUC:
    def __init__(self, availability: IBuildAvailability) -> None:
        self._availability = availability

    async def execute(self, inp: GetBuildAvailabilityInput) -> BuildAvailability:
        return await self._availability.of(inp.project_id, current_actor() or Actor.local())


class GetGeneralBuildAvailabilityUC:
    """Без проекта: живы ли общие раннеры установки (итог онбординга говорит об этом честно)."""

    def __init__(self, availability: IBuildAvailability) -> None:
        self._availability = availability

    async def execute(self) -> BuildAvailability:
        return await self._availability.general()
