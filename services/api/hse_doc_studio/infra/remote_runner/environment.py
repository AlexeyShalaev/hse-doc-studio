"""Машина Студии глазами облачных сборок: Docker, активный образ TeX и занятость локальных сборок."""

from __future__ import annotations

from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.docker.cli import image_present
from hse_doc_studio.infra.update.deployment import docker_alive
from hse_doc_studio.use_cases.compile.list_images import resolve_active_image


class LocalRunnerEnvironment:
    def __init__(self, settings_repo: ISettingsRepository, dispatcher: IJobDispatcher) -> None:
        self._settings_repo = settings_repo
        self._dispatcher = dispatcher

    async def docker_available(self) -> bool:
        return await docker_alive()

    async def tex_image(self) -> str:
        # Тот же образ, что у локальных сборок: облачная сборка не тянет второй образ на несколько гигабайт.
        return await resolve_active_image(self._settings_repo)

    async def image_present(self, image: str) -> bool:
        return await image_present(image)

    def local_busy(self) -> bool:
        return self._dispatcher.has_any_active()
