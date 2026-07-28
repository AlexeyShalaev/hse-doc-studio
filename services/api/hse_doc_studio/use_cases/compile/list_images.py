from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.docker_image_manager import (
    DockerImageManager,
    LocalImageInfo,
)


@dataclass
class ListImagesOutput:
    active_image: str
    allowed_repos: list[str]
    installed: list[LocalImageInfo]


class ListImagesUC:
    """Returns the active image, list of installed local images, and the repos
    the UI is allowed to manage.

    Used to render the Settings → Образы list: which tag is in use right now,
    which tags are already pulled (so removable / activatable), and which
    repos can be queried for remote tags.
    """

    def __init__(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._image_manager = image_manager
        self._settings_repo = settings_repo

    async def execute(self) -> ListImagesOutput:
        active = resolve_active_image(self._settings_repo)
        repos = settings.compile.allowed_repos
        installed: list[LocalImageInfo] = []
        for repo in repos:
            installed.extend(await self._image_manager.list_local(repo))
        return ListImagesOutput(
            active_image=active,
            allowed_repos=list(repos),
            installed=installed,
        )


def resolve_active_image(settings_repo: ISettingsRepository) -> str:
    """Return the image tag the next compile will use.

    User-configured `compile_image` in settings.json wins; if absent or empty
    we fall back to the deployment-level default in `api.config`.
    """
    stored = settings_repo.get()
    user_choice = stored.get("compile_image")
    if isinstance(user_choice, str) and user_choice.strip():
        return user_choice
    return settings.compile.image
