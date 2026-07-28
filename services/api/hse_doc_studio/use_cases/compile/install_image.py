from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager


@dataclass
class InstallImageInput:
    image: str


class InstallImageUC:
    """Streams `docker pull <image>` progress for the install UI.

    Only images whose repo is in the configured allowlist are accepted —
    accepting an arbitrary user-supplied tag would let the API trigger
    pulls of any image on Docker Hub, both a footgun and a security smell.
    """

    def __init__(self, image_manager: DockerImageManager) -> None:
        self._image_manager = image_manager

    async def execute(self, inp: InstallImageInput) -> AsyncGenerator[str, None]:
        if not _repo_allowed(inp.image, settings.compile.allowed_repos):
            raise ValueError(
                localized_error(
                    f"образ не входит в список разрешённых репозиториев: {inp.image}",
                    f"image not in allowed repos: {inp.image}",
                )
            )
        return await self._image_manager.pull(inp.image)


def _repo_allowed(image: str, allowed: list[str]) -> bool:
    if ":" not in image:
        return False
    repo, _, _ = image.partition(":")
    return repo in allowed
