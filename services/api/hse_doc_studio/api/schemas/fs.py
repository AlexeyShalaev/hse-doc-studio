from __future__ import annotations

from pydantic import BaseModel


class BrowseEntryResponse(BaseModel):
    name: str
    path: str
    is_dir: bool
    is_hidden: bool


class BrowseResponse(BaseModel):
    path: str
    parent: str | None
    entries: list[BrowseEntryResponse]
    # Корень смонтированной папки пользователя: выше подниматься некуда, а сам
    # каталог уже пригоден для выбора без дополнительной навигации.
    is_root: bool = False


class InspectedProjectResponse(BaseModel):
    id: str
    name: str
    pack_id: str
    template_id: str
    version: str
    engine: str


class InspectResponse(BaseModel):
    path: str
    exists: bool
    is_dir: bool
    has_project: bool
    project: InspectedProjectResponse | None
