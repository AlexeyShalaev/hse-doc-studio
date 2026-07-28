"""Office services (Gotenberg convert + ONLYOFFICE editor) image-management schemas.

Зеркало `api/schemas/languagetool.py`: те же формы ошибок и тот же SSE-формат
установки, чтобы фронт переиспользовал готовые типы LT-секции.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OfficeServiceContainerResponse(BaseModel):
    present: bool
    running: bool
    status_text: str | None


class OfficeServiceStatusResponse(BaseModel):
    service: str = Field(description='"convert" (Gotenberg) | "editor" (ONLYOFFICE)')
    label_hint: str = Field(description='"gotenberg" | "onlyoffice" — подсказка фронту, не для логики')
    active_image: str
    image_installed: bool
    container: OfficeServiceContainerResponse


class OfficeServicesStatusResponse(BaseModel):
    services: list[OfficeServiceStatusResponse]


class OfficeServiceImageResponse(BaseModel):
    tag: str = Field(description='Полная ссылка образа "repo:tag", напр. "gotenberg/gotenberg:8"')
    size: int = Field(description="Размер в байтах")
    created: str
    active: bool
    installed: bool


class OfficeServiceImagesListResponse(BaseModel):
    active_image: str
    allowed_repos: list[str]
    images: list[OfficeServiceImageResponse]


class OfficeServiceRemoteTagResponse(BaseModel):
    name: str
    size_bytes: int
    last_updated: str | None


class OfficeServiceRemoteTagsResponse(BaseModel):
    repo: str
    tags: list[OfficeServiceRemoteTagResponse]


class SetActiveOfficeServiceImageRequest(BaseModel):
    image: str


class SetActiveOfficeServiceImageResponse(BaseModel):
    image: str
