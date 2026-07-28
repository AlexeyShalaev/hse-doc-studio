from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.infra.compile.docker_image_manager import (
    DockerImageManager,
    RemoteTagInfo,
)
from hse_doc_studio.use_cases.office_services.list_office_service_images import (
    office_service_config,
)


@dataclass
class ListOfficeServiceRemoteTagsInput:
    service: str
    # None → первый (единственный) репозиторий из allowlist сервиса.
    repo: str | None = None


@dataclass
class ListOfficeServiceRemoteTagsOutput:
    repo: str
    tags: list[RemoteTagInfo]


class ListOfficeServiceRemoteTagsUC:
    """Lists Docker Hub tags for an allowed office-service repo.

    Same pagination/limits as LanguageTool: DockerImageManager fetches the
    first Docker Hub page (newest first, page_size=100).
    """

    def __init__(self, image_manager: DockerImageManager) -> None:
        self._image_manager = image_manager

    async def execute(self, inp: ListOfficeServiceRemoteTagsInput) -> ListOfficeServiceRemoteTagsOutput:
        cfg = office_service_config(inp.service)
        repo = inp.repo if inp.repo is not None else next(iter(cfg.allowed_repos), None)
        if repo is None or repo not in cfg.allowed_repos:
            raise ValueError(localized_error(f"репозиторий не разрешён: {inp.repo}", f"repo not allowed: {inp.repo}"))
        tags = await self._image_manager.list_remote_tags(repo, cfg.docker_hub_base)
        return ListOfficeServiceRemoteTagsOutput(repo=repo, tags=tags)
