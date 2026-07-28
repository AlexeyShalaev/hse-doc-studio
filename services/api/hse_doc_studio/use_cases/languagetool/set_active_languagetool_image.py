from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.use_cases.languagetool.list_languagetool_images import (
    languagetool_repo_allowed,
)


@dataclass
class SetActiveLanguageToolImageInput:
    image: str


@dataclass
class SetActiveLanguageToolImageOutput:
    image: str


class SetActiveLanguageToolImageUC:
    """Persists the chosen LanguageTool image (config.json `languagetool_image`).

    Allowlist-gated and requires the image to be installed locally — same
    guards as the compile-image activation.
    """

    def __init__(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._image_manager = image_manager
        self._settings_repo = settings_repo

    async def execute(self, inp: SetActiveLanguageToolImageInput) -> SetActiveLanguageToolImageOutput:
        if not languagetool_repo_allowed(inp.image, settings.languagetool.allowed_repos):
            raise ValueError(
                localized_error(
                    f"образ не входит в список разрешённых репозиториев: {inp.image}",
                    f"image not in allowed repos: {inp.image}",
                )
            )
        if await self._image_manager.inspect(inp.image) is None:
            raise ValueError(
                localized_error(
                    f"образ не установлен локально: {inp.image}", f"image not installed locally: {inp.image}"
                )
            )
        stored = self._settings_repo.get()
        stored["languagetool_image"] = inp.image
        self._settings_repo.save(stored)
        return SetActiveLanguageToolImageOutput(image=inp.image)
