from __future__ import annotations

from pydantic import BaseModel


class LanguageToolStatusResponse(BaseModel):
    docker_available: bool
    docker_detail: str | None
    docker_reason: str | None = None
    docker_socket_gid: int | None = None
    active_image: str
    image_installed: bool
    container_present: bool
    container_running: bool
    container_status: str | None
    healthy: bool
    base_url: str | None


class LanguageToolImageResponse(BaseModel):
    image: str
    repository: str
    tag: str
    id: str
    size_bytes: int
    created: str


class LanguageToolImagesListResponse(BaseModel):
    active_image: str
    allowed_repos: list[str]
    installed: list[LanguageToolImageResponse]


class LanguageToolRemoteTagResponse(BaseModel):
    name: str
    size_bytes: int
    last_updated: str | None


class LanguageToolRemoteTagsResponse(BaseModel):
    repo: str
    tags: list[LanguageToolRemoteTagResponse]


class SetActiveLanguageToolImageRequest(BaseModel):
    image: str


class SetActiveLanguageToolImageResponse(BaseModel):
    image: str
