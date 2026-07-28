from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.infra.compile.docker_image_manager import (
    DockerImageManager,
    LocalImageInfo,
)


@dataclass
class ListLanguageToolImagesOutput:
    active_image: str
    allowed_repos: list[str]
    installed: list[LocalImageInfo]


class ListLanguageToolImagesUC:
    """Lists installed LanguageTool images + the active one for the Settings UI.

    Reuses the repo-agnostic DockerImageManager — same `docker images` calls as
    the compile-image list, just scoped to the LanguageTool allowlist.
    """

    def __init__(
        self,
        image_manager: DockerImageManager,
        settings_repo: ISettingsRepository,
    ) -> None:
        self._image_manager = image_manager
        self._settings_repo = settings_repo

    async def execute(self) -> ListLanguageToolImagesOutput:
        active = resolve_active_languagetool_image(self._settings_repo)
        repos = settings.languagetool.allowed_repos
        installed: list[LocalImageInfo] = []
        for repo in repos:
            installed.extend(await self._image_manager.list_local(repo))
        return ListLanguageToolImagesOutput(
            active_image=active,
            allowed_repos=list(repos),
            installed=installed,
        )


def resolve_active_languagetool_image(settings_repo: ISettingsRepository) -> str:
    """Return the LanguageTool image the managed container will run.

    User-configured `languagetool_image` in settings.json wins; if absent or
    empty we fall back to the deployment-level default in api.config.
    """
    stored = settings_repo.get()
    choice = stored.get("languagetool_image")
    if isinstance(choice, str) and choice.strip():
        return choice
    return settings.languagetool.image


def languagetool_repo_allowed(image: str, allowed: list[str]) -> bool:
    """True if `image` is a tagged ref whose repo is in the LanguageTool allowlist."""
    if ":" not in image:
        return False
    repo, _, _ = image.partition(":")
    return repo in allowed
