from __future__ import annotations

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.git_sync import ProfileRequest, ProfileResponse
from hse_doc_studio.core.vcs.errors import ProfileInvalidError
from hse_doc_studio.use_cases.profile.clear_profile import ClearProfileUC
from hse_doc_studio.use_cases.profile.get_profile import GetProfileUC
from hse_doc_studio.use_cases.profile.profile_view import ProfileView
from hse_doc_studio.use_cases.profile.update_profile import UpdateProfileInput, UpdateProfileUC

router = APIRouter(route_class=SafeDishkaRoute)


def _map_profile(view: ProfileView) -> ProfileResponse:
    profile = view.profile
    return ProfileResponse(
        name=None if profile is None else profile.name,
        email=None if profile is None else profile.email,
        effective_name=view.effective.name,
        effective_email=view.effective.email,
        is_default=view.is_default,
        commit_preview=view.commit_preview,
    )


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(uc: FromDishka[GetProfileUC]) -> ProfileResponse:
    return _map_profile(await uc.execute())


@router.put("/profile", response_model=ProfileResponse)
async def update_profile(body: ProfileRequest, uc: FromDishka[UpdateProfileUC]) -> ProfileResponse:
    try:
        view = await uc.execute(UpdateProfileInput(name=body.name, email=body.email))
    except ProfileInvalidError as exc:
        # Тот же вид, что у ошибок проверки FastAPI, плюс код правила для подсветки поля.
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["body", e.field], "code": e.code, "msg": e.message} for e in exc.errors],
        ) from exc
    return _map_profile(view)


@router.delete("/profile", response_model=ProfileResponse)
async def clear_profile(uc: FromDishka[ClearProfileUC]) -> ProfileResponse:
    return _map_profile(await uc.execute())
