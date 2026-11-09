from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class InstalledFontResponse(BaseModel):
    name: str
    size_bytes: int
    family: str = ""


class FontsListResponse(BaseModel):
    fonts: list[InstalledFontResponse]


class FontCatalogItemResponse(BaseModel):
    id: str
    label: str
    family: str
    description: str
    license: str
    file_count: int
    installed: bool


class FontCatalogResponse(BaseModel):
    items: list[FontCatalogItemResponse]


class InstallFontResponse(BaseModel):
    installed: list[InstalledFontResponse]


class SystemFontResponse(BaseModel):
    name: str
    path: str
    family: str
    already_installed: bool


class SystemFontsListResponse(BaseModel):
    # available=False → host exposes no font directories (e.g. containerized).
    available: bool
    fonts: list[SystemFontResponse]
    # Почему списка нет: «not_shared» — докер не отдал каталог шрифтов машины
    # (Docker Desktop на macOS не пускает в /System), «not_found» — их там нет.
    reason: Literal["not_shared", "not_found"] | None = None


class ImportSystemFontsRequest(BaseModel):
    paths: list[str]


class MarketplaceFontResponse(BaseModel):
    id: str
    family: str
    category: str
    cyrillic: bool
    file_count: int


class MarketplaceSearchResponse(BaseModel):
    total: int
    items: list[MarketplaceFontResponse]
