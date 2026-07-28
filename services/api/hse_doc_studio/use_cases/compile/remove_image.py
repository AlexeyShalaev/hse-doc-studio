from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.use_cases.compile.list_images import resolve_active_image


@dataclass
class RemoveImageInput:
    image: str


@dataclass
class RemoveImageOutput:
    image: str


class RemoveImageUC:
    """Deletes a local Docker image after guarding against removing the active one.

    Refuses to nuke the image the next Сборка would use — that lets us avoid a
    surprise preflight failure right after the user clicks Удалить in a UI
    that didn't realise the row was the active one.
    """

    def __init__(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._image_manager = image_manager
        self._settings_repo = settings_repo

    async def execute(self, inp: RemoveImageInput) -> RemoveImageOutput:
        active = resolve_active_image(self._settings_repo)
        if inp.image == active:
            raise ValueError(
                localized_error(
                    "нельзя удалить активный образ — сначала переключите активный образ",
                    "cannot remove the active image; switch active image first",
                ),
            )
        removed, detail = await self._image_manager.remove(inp.image)
        if not removed:
            raise ValueError(detail or localized_error("не удалось удалить образ Docker", "docker image rm failed"))
        return RemoveImageOutput(image=inp.image)
