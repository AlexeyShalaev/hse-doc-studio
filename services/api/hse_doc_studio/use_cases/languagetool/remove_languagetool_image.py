from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.use_cases.languagetool.list_languagetool_images import (
    resolve_active_languagetool_image,
)


@dataclass
class RemoveLanguageToolImageInput:
    image: str


class RemoveLanguageToolImageUC:
    """Removes a local LanguageTool image, refusing to remove the active one."""

    def __init__(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._image_manager = image_manager
        self._settings_repo = settings_repo

    async def execute(self, inp: RemoveLanguageToolImageInput) -> None:
        if inp.image == resolve_active_languagetool_image(self._settings_repo):
            raise ValueError(
                localized_error(
                    "нельзя удалить активный образ LanguageTool", "cannot remove the active LanguageTool image"
                )
            )
        removed, detail = await self._image_manager.remove(inp.image)
        if not removed:
            raise ValueError(detail or localized_error("не удалось удалить образ Docker", "docker image rm failed"))
