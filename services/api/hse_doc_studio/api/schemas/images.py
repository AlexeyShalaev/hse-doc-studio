from __future__ import annotations

from pydantic import BaseModel


class DockerStatusResponse(BaseModel):
    available: bool
    version: str | None
    detail: str | None
    # Код причины + gid владельца сокета: по ним фронтенд рисует локализованную
    # подсказку с готовой командой вместо сырого stderr докера.
    reason: str | None = None
    socket_gid: int | None = None


class LocalImageResponse(BaseModel):
    image: str
    repository: str
    tag: str
    id: str
    size_bytes: int
    created: str


class RemoteTagResponse(BaseModel):
    name: str
    size_bytes: int
    last_updated: str | None


class ImagesListResponse(BaseModel):
    active_image: str
    allowed_repos: list[str]
    installed: list[LocalImageResponse]


class RemoteTagsResponse(BaseModel):
    repo: str
    tags: list[RemoteTagResponse]


class SetActiveImageRequest(BaseModel):
    image: str


class SetActiveImageResponse(BaseModel):
    image: str
