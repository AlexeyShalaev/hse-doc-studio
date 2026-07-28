from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.infra.languagetool.container_manager import (
    ContainerState,
    LanguageToolContainerManager,
)
from hse_doc_studio.use_cases.languagetool.list_languagetool_images import (
    resolve_active_languagetool_image,
)


@dataclass
class LanguageToolStatusOutput:
    docker_available: bool
    docker_detail: str | None
    # Причина и gid сокета — те же, что у GET /compile/docker-status: подсказку
    # с починкой фронтенд рисует одним компонентом в обоих местах.
    docker_reason: str | None
    docker_socket_gid: int | None
    active_image: str
    image_installed: bool
    container_present: bool
    container_running: bool
    container_status: str | None
    healthy: bool
    base_url: str | None


class GetLanguageToolStatusUC:
    """Aggregates what the Settings UI needs to render LanguageTool state:
    Docker availability, whether the active image is installed, and the
    auto-managed container's presence / running / health / live endpoint.
    There is no enable flag or configurable URL — installing the image is the
    opt-in and the container is started on demand by the check pipeline.
    """

    def __init__(
        self,
        container_manager: LanguageToolContainerManager,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._container_manager = container_manager
        self._image_manager = image_manager
        self._settings_repo = settings_repo

    async def execute(self) -> LanguageToolStatusOutput:
        active_image = resolve_active_languagetool_image(self._settings_repo)

        docker_status = await self._image_manager.docker_status()
        image_installed = False
        container = ContainerState.absent()
        healthy = False
        if docker_status.available:
            image_installed = await self._image_manager.inspect(active_image) is not None
            container = await self._container_manager.inspect_container()
            if container.running:
                healthy = await self._container_manager.is_healthy()

        return LanguageToolStatusOutput(
            docker_available=docker_status.available,
            docker_detail=docker_status.detail,
            docker_reason=str(docker_status.reason) if docker_status.reason else None,
            docker_socket_gid=docker_status.socket_gid,
            active_image=active_image,
            image_installed=image_installed,
            container_present=container.present,
            container_running=container.running,
            container_status=container.status_text,
            healthy=healthy,
            base_url=self._container_manager.current_base_url,
        )
