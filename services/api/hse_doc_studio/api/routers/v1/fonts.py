from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query, Request, Response

from hse_doc_studio.api.schemas.fonts import (
    FontCatalogItemResponse,
    FontCatalogResponse,
    FontsListResponse,
    ImportSystemFontsRequest,
    InstalledFontResponse,
    InstallFontResponse,
    MarketplaceFontResponse,
    MarketplaceSearchResponse,
    SystemFontResponse,
    SystemFontsListResponse,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.fonts.get_font_file import GetFontFileInput, GetFontFileUC
from hse_doc_studio.use_cases.fonts.import_system_fonts import (
    ImportSystemFontsInput,
    ImportSystemFontsUC,
)
from hse_doc_studio.use_cases.fonts.install_font import InstallFontInput, InstallFontUC
from hse_doc_studio.use_cases.fonts.install_marketplace_font import (
    InstallMarketplaceFontInput,
    InstallMarketplaceFontUC,
)
from hse_doc_studio.use_cases.fonts.list_font_catalog import ListFontCatalogUC
from hse_doc_studio.use_cases.fonts.list_fonts import ListFontsUC
from hse_doc_studio.use_cases.fonts.list_system_fonts import ListSystemFontsUC
from hse_doc_studio.use_cases.fonts.remove_font import RemoveFontInput, RemoveFontUC
from hse_doc_studio.use_cases.fonts.search_marketplace import SearchMarketplaceInput, SearchMarketplaceUC
from hse_doc_studio.use_cases.fonts.upload_font import UploadFontInput, UploadFontUC

router = APIRouter(route_class=DishkaRoute)

_FONT_MEDIA_TYPES: dict[str, str] = {
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".ttc": "font/collection",
}


@router.get("/fonts", response_model=FontsListResponse)
async def list_fonts(uc: FromDishka[ListFontsUC]) -> FontsListResponse:
    result = await uc.execute()
    return FontsListResponse(
        fonts=[InstalledFontResponse(name=f.name, size_bytes=f.size_bytes, family=f.family) for f in result.fonts]
    )


@router.get("/fonts/{filename}/file")
async def get_font_file(filename: str, uc: FromDishka[GetFontFileUC]) -> Response:
    # Serves a managed font's bytes so the UI can preview it via @font-face.
    try:
        out = await uc.execute(GetFontFileInput(filename=filename))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    suffix = ("." + out.filename.rsplit(".", 1)[-1].lower()) if "." in out.filename else ""
    return Response(
        content=out.content,
        media_type=_FONT_MEDIA_TYPES.get(suffix, "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/fonts/catalog", response_model=FontCatalogResponse)
async def list_font_catalog(uc: FromDishka[ListFontCatalogUC]) -> FontCatalogResponse:
    result = await uc.execute()
    return FontCatalogResponse(
        items=[
            FontCatalogItemResponse(
                id=i.id,
                label=i.label,
                family=i.family,
                description=i.description,
                license=i.license,
                file_count=i.file_count,
                installed=i.installed,
            )
            for i in result.items
        ]
    )


@router.get("/fonts/system", response_model=SystemFontsListResponse)
async def list_system_fonts(uc: FromDishka[ListSystemFontsUC]) -> SystemFontsListResponse:
    result = await uc.execute()
    return SystemFontsListResponse(
        available=result.available,
        fonts=[
            SystemFontResponse(name=f.name, path=f.path, family=f.family, already_installed=f.already_installed)
            for f in result.fonts
        ],
    )


@router.post("/fonts/system/import", response_model=InstallFontResponse)
async def import_system_fonts(
    body: ImportSystemFontsRequest, uc: FromDishka[ImportSystemFontsUC]
) -> InstallFontResponse:
    try:
        result = await uc.execute(ImportSystemFontsInput(paths=body.paths))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return InstallFontResponse(
        installed=[
            InstalledFontResponse(name=f.name, size_bytes=f.size_bytes, family=f.family) for f in result.installed
        ]
    )


@router.get("/fonts/marketplace", response_model=MarketplaceSearchResponse)
async def search_marketplace(
    uc: FromDishka[SearchMarketplaceUC],
    q: str = "",
    category: str | None = None,
    cyrillic: bool = True,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> MarketplaceSearchResponse:
    out = await uc.execute(
        SearchMarketplaceInput(query=q, category=category, cyrillic_only=cyrillic, limit=limit, offset=offset)
    )
    return MarketplaceSearchResponse(
        total=out.result.total,
        items=[
            MarketplaceFontResponse(
                id=f.id, family=f.family, category=f.category, cyrillic=f.cyrillic, file_count=f.file_count
            )
            for f in out.result.items
        ],
    )


@router.post("/fonts/marketplace/{font_id}", response_model=InstallFontResponse)
async def install_marketplace_font(font_id: str, uc: FromDishka[InstallMarketplaceFontUC]) -> InstallFontResponse:
    try:
        result = await uc.execute(InstallMarketplaceFontInput(id=font_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return InstallFontResponse(
        installed=[
            InstalledFontResponse(name=f.name, size_bytes=f.size_bytes, family=f.family) for f in result.installed
        ]
    )


@router.post("/fonts/catalog/{font_id}", response_model=InstallFontResponse)
async def install_catalog_font(font_id: str, uc: FromDishka[InstallFontUC]) -> InstallFontResponse:
    try:
        result = await uc.execute(InstallFontInput(id=font_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return InstallFontResponse(
        installed=[
            InstalledFontResponse(name=f.name, size_bytes=f.size_bytes, family=f.family) for f in result.installed
        ]
    )


@router.put("/fonts/{filename}", response_model=InstalledFontResponse)
async def upload_font(filename: str, request: Request, uc: FromDishka[UploadFontUC]) -> InstalledFontResponse:
    # Raw binary body (mirrors files.put_file); the filename rides in the path.
    content = await request.body()
    try:
        result = await uc.execute(UploadFontInput(filename=filename, content=content))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return InstalledFontResponse(name=result.font.name, size_bytes=result.font.size_bytes, family=result.font.family)


@router.delete("/fonts/{filename}", status_code=204)
async def remove_font(filename: str, uc: FromDishka[RemoveFontUC]) -> None:
    try:
        await uc.execute(RemoveFontInput(name=filename))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
