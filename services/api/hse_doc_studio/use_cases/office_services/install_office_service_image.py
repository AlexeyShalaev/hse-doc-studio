from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.use_cases.office_services.list_office_service_images import (
    office_repo_allowed,
    office_service_config,
)


@dataclass
class InstallOfficeServiceImageInput:
    service: str
    image: str


class InstallOfficeServiceImageUC:
    """Streams `docker pull <image>` progress for the office-service install UI.

    Gated by the per-service allowlist so the API can't be used to pull
    arbitrary Docker Hub images (mirrors InstallLanguageToolImageUC).
    """

    def __init__(self, image_manager: DockerImageManager) -> None:
        self._image_manager = image_manager

    async def execute(self, inp: InstallOfficeServiceImageInput) -> AsyncGenerator[str, None]:
        cfg = office_service_config(inp.service)
        if not office_repo_allowed(inp.image, cfg.allowed_repos):
            raise ValueError(
                localized_error(
                    f"образ не входит в список разрешённых репозиториев: {inp.image}",
                    f"image not in allowed repos: {inp.image}",
                )
            )
        return await self._image_manager.pull(inp.image)
