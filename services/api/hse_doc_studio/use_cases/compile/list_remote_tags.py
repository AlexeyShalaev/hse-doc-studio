from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.infra.compile.docker_image_manager import (
    DockerImageManager,
    RemoteTagInfo,
)


@dataclass
class ListRemoteTagsInput:
    repo: str


@dataclass
class ListRemoteTagsOutput:
    repo: str
    tags: list[RemoteTagInfo]


class ListRemoteTagsUC:
    """Lists tags published on Docker Hub for one of the allowed repos.

    Allowlist guard: refusing arbitrary repo names is important even though
    nothing past this point pulls or runs them — clients shouldn't be able
    to use our backend as a proxy to enumerate any repo on Docker Hub.
    """

    def __init__(self, image_manager: DockerImageManager) -> None:
        self._image_manager = image_manager

    async def execute(self, inp: ListRemoteTagsInput) -> ListRemoteTagsOutput:
        if inp.repo not in settings.compile.allowed_repos:
            raise ValueError(
                localized_error(
                    f"репозиторий не в списке разрешённых: {inp.repo}", f"repo not in allowlist: {inp.repo}"
                )
            )
        tags = await self._image_manager.list_remote_tags(inp.repo, settings.compile.docker_hub_base)
        return ListRemoteTagsOutput(repo=inp.repo, tags=tags)
