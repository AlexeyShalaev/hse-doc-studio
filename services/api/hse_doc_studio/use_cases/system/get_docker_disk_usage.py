from __future__ import annotations

from hse_doc_studio.core.docker_disk.planner import DockerDiskPlanner, DockerDiskProbe, DockerDiskSnapshot
from hse_doc_studio.core.repositories import ISettingsRepository

# Ответ замера локального «Диска»; правила общие с раннером (core/docker_disk).
GetDockerDiskUsageOutput = DockerDiskSnapshot


class GetDockerDiskUsageUC:
    def __init__(
        self,
        manager: DockerDiskProbe,
        settings_repo: ISettingsRepository,
        default_images: dict[str, str],
        always_protected: frozenset[str],
        current_version: str = "",
        image_base: str = "",
    ) -> None:
        self._manager = manager
        self._settings_repo = settings_repo
        self._default_images = dict(default_images)
        self._always_protected = always_protected
        self._current_version = current_version
        self._image_base = image_base

    async def execute(self) -> GetDockerDiskUsageOutput:
        return await (await self.planner()).measure()

    async def planner(self) -> DockerDiskPlanner:
        """Планировщик с защитой по текущим настройкам: выбранный образ каждой категории не удаляется."""
        return DockerDiskPlanner(
            self._manager,
            protected_refs=await self.protected_refs(),
            current_version=self._current_version,
            image_base=self._image_base,
        )

    async def protected_refs(self) -> frozenset[str]:
        """Images that must survive cleanup: each category's configured/active ref."""
        stored = await self._settings_repo.get()
        refs = {str(stored.get(key) or default) for key, default in self._default_images.items()}
        return frozenset(refs) | self._always_protected
