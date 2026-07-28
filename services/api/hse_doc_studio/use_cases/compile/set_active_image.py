from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager


@dataclass
class SetActiveImageInput:
    image: str


@dataclass
class SetActiveImageOutput:
    image: str


class SetActiveImageUC:
    """Persists the chosen LaTeX image to user settings.

    Only allows tags from the configured `allowed_repos` so the API can't be
    used to point compilation at an arbitrary Docker Hub image. The image
    must already be installed locally — activating a tag the daemon has
    never seen would just make the next Сборка fail preflight, which is
    worse UX than refusing the activation up front.
    """

    def __init__(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._image_manager = image_manager
        self._settings_repo = settings_repo

    async def execute(self, inp: SetActiveImageInput) -> SetActiveImageOutput:
        if not _is_in_allowed_repos(inp.image, settings.compile.allowed_repos):
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
        stored["compile_image"] = inp.image
        self._settings_repo.save(stored)
        return SetActiveImageOutput(image=inp.image)


def _is_in_allowed_repos(image: str, allowed: list[str]) -> bool:
    if ":" not in image:
        return False
    repo, _, _ = image.partition(":")
    return repo in allowed
