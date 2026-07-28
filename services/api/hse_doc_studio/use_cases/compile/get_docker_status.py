from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager, DockerStatus


@dataclass
class GetDockerStatusOutput:
    status: DockerStatus


class GetDockerStatusUC:
    def __init__(self, image_manager: DockerImageManager) -> None:
        self._image_manager = image_manager

    async def execute(self) -> GetDockerStatusOutput:
        status = await self._image_manager.docker_status()
        return GetDockerStatusOutput(status=status)
