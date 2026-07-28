from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.infra.compile.docker_image_manager import (
    DockerImageManager,
    RemoteTagInfo,
)


@dataclass
class ListLanguageToolRemoteTagsInput:
    repo: str


@dataclass
class ListLanguageToolRemoteTagsOutput:
    repo: str
    tags: list[RemoteTagInfo]


class ListLanguageToolRemoteTagsUC:
    """Lists Docker Hub tags for an allowed LanguageTool repo."""

    def __init__(self, image_manager: DockerImageManager) -> None:
        self._image_manager = image_manager

    async def execute(self, inp: ListLanguageToolRemoteTagsInput) -> ListLanguageToolRemoteTagsOutput:
        if inp.repo not in settings.languagetool.allowed_repos:
            raise ValueError(localized_error(f"репозиторий не разрешён: {inp.repo}", f"repo not allowed: {inp.repo}"))
        tags = await self._image_manager.list_remote_tags(inp.repo, settings.languagetool.docker_hub_base)
        return ListLanguageToolRemoteTagsOutput(repo=inp.repo, tags=tags)
