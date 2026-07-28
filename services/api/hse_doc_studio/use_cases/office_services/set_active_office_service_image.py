from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager
from hse_doc_studio.use_cases.office_services.list_office_service_images import (
    office_repo_allowed,
    office_service_config,
    office_service_settings_key,
)


@dataclass
class SetActiveOfficeServiceImageInput:
    service: str
    image: str


@dataclass
class SetActiveOfficeServiceImageOutput:
    image: str


class SetActiveOfficeServiceImageUC:
    """Persists the chosen office-service image (config.json
    `office_convert_image` / `office_editor_image`).

    Allowlist-gated and requires the image to be installed locally — same
    guards as the LanguageTool/compile-image activation.
    """

    def __init__(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._image_manager = image_manager
        self._settings_repo = settings_repo

    async def execute(self, inp: SetActiveOfficeServiceImageInput) -> SetActiveOfficeServiceImageOutput:
        cfg = office_service_config(inp.service)
        if not office_repo_allowed(inp.image, cfg.allowed_repos):
            raise ValueError(
                localized_error(
                    f"образ не входит в список разрешённых репозиториев: {inp.image}",
                    f"image not in allowed repos: {inp.image}",
                )
            )
        if await self._image_manager.inspect(inp.image) is None:
            raise NotFoundError(
                localized_error(
                    f"образ не установлен локально: {inp.image}", f"image not installed locally: {inp.image}"
                )
            )
        stored = self._settings_repo.get()
        stored[office_service_settings_key(inp.service)] = inp.image
        self._settings_repo.save(stored)
        return SetActiveOfficeServiceImageOutput(image=inp.image)
