from __future__ import annotations

from pydantic import BaseModel


class HseFacetOptionResponse(BaseModel):
    value: str
    label: str


class HsePersonSummaryResponse(BaseModel):
    id: str
    full_name: str
    profile_url: str
    photo_url: str
    affiliation: str


class HsePersonDetailResponse(BaseModel):
    id: str
    full_name: str
    position: str
    department: str
    degree: str
    profile_url: str
    photo_url: str


class HseSearchResponse(BaseModel):
    persons: list[HsePersonSummaryResponse]
    interests: list[HseFacetOptionResponse]


class HseFacetsResponse(BaseModel):
    campuses: list[HseFacetOptionResponse]
    departments: list[HseFacetOptionResponse]
    categories: list[HseFacetOptionResponse]
    sciranks: list[HseFacetOptionResponse]
    positions: list[HseFacetOptionResponse]
