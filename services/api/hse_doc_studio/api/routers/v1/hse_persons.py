from __future__ import annotations

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query

from hse_doc_studio.api.schemas.hse_persons import (
    HseFacetOptionResponse,
    HseFacetsResponse,
    HsePersonDetailResponse,
    HsePersonSummaryResponse,
    HseSearchResponse,
)
from hse_doc_studio.core.hse_persons.entities import HseFacetOption, HseFacets, HseSearchResult
from hse_doc_studio.use_cases.hse_persons.get_facets import GetHseFacetsInput, GetHseFacetsUC
from hse_doc_studio.use_cases.hse_persons.get_person_detail import (
    GetHsePersonDetailInput,
    GetHsePersonDetailUC,
)
from hse_doc_studio.use_cases.hse_persons.search_persons import SearchHsePersonsInput, SearchHsePersonsUC

router = APIRouter(route_class=DishkaRoute, prefix="/hse/persons")

_MAX_LIMIT = 60


def _option(o: HseFacetOption) -> HseFacetOptionResponse:
    return HseFacetOptionResponse(value=o.value, label=o.label)


def _to_facets(facets: HseFacets) -> HseFacetsResponse:
    return HseFacetsResponse(
        campuses=[_option(o) for o in facets.campuses],
        departments=[_option(o) for o in facets.departments],
        categories=[_option(o) for o in facets.categories],
        sciranks=[_option(o) for o in facets.sciranks],
        positions=[_option(o) for o in facets.positions],
    )


def _to_search(result: HseSearchResult) -> HseSearchResponse:
    return HseSearchResponse(
        persons=[
            HsePersonSummaryResponse(
                id=p.id,
                full_name=p.full_name,
                profile_url=p.profile_url,
                photo_url=p.photo_url,
                affiliation=p.affiliation,
            )
            for p in result.persons
        ],
        interests=[_option(o) for o in result.interests],
    )


# NOTE: static sub-paths (/facets) MUST be declared before /{person_id} so the
# path param doesn't capture them.
@router.get("/facets", response_model=HseFacetsResponse)
async def get_facets(uc: FromDishka[GetHseFacetsUC], campus: str = Query(default="")) -> HseFacetsResponse:
    return _to_facets(await uc.execute(GetHseFacetsInput(campus=campus)))


@router.get("/search", response_model=HseSearchResponse)
async def search_persons(
    uc: FromDishka[SearchHsePersonsUC],
    q: str = Query(default=""),
    campus: str = Query(default=""),
    udept: str = Query(default=""),
    ltr: str = Query(default=""),
    category: str = Query(default=""),
    scirank: str = Query(default=""),
    position: str = Query(default=""),
    intst: str = Query(default=""),
    limit: int = Query(default=40, ge=1, le=_MAX_LIMIT),
) -> HseSearchResponse:
    result = await uc.execute(
        SearchHsePersonsInput(
            name=q,
            campus=campus,
            udept=udept,
            ltr=ltr,
            category=category,
            scirank=scirank,
            position=position,
            intst=intst,
            limit=limit,
        )
    )
    return _to_search(result)


@router.get("/{person_id}", response_model=HsePersonDetailResponse)
async def get_person_detail(person_id: str, uc: FromDishka[GetHsePersonDetailUC]) -> HsePersonDetailResponse:
    detail = await uc.execute(GetHsePersonDetailInput(person_id=person_id))
    if detail is None:
        raise HTTPException(status_code=404, detail="HSE person not found or directory unavailable")
    return HsePersonDetailResponse(
        id=detail.id,
        full_name=detail.full_name,
        position=detail.position,
        department=detail.department,
        degree=detail.degree,
        profile_url=detail.profile_url,
        photo_url=detail.photo_url,
    )
