from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.use_cases.languagetool.list_languagetool_images import (
    languagetool_repo_allowed,
)


@dataclass
class InstallLanguageToolImageInput:
    image: str


class InstallLanguageToolImageUC:
    """Streams `docker pull <image>` progress for the LanguageTool install UI.

    Gated by the LanguageTool allowlist so the API can't be used to pull
    arbitrary Docker Hub images.
    """

    def __init__(self, image_manager: DockerImageManager) -> None:
        self._image_manager = image_manager

    async def execute(self, inp: InstallLanguageToolImageInput) -> AsyncGenerator[str, None]:
        if not languagetool_repo_allowed(inp.image, settings.languagetool.allowed_repos):
            raise ValueError(
                localized_error(
                    f"образ не входит в список разрешённых репозиториев: {inp.image}",
                    f"image not in allowed repos: {inp.image}",
                )
            )
        return await self._image_manager.pull(inp.image)
