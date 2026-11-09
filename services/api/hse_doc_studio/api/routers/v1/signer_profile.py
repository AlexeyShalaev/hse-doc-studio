"""Свой профиль подписанта: картинка подписи и сертификат или открытый ключ для плашки (только сервер).

Путь не содержит id пользователя: каждый маршрут работает с профилем того, кто вошёл, поэтому чужой профиль не
прочитать и не изменить. Гость по ссылке профиля не имеет. Закрытый ключ в профиль не принимается (400).
"""

from __future__ import annotations

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.signer_profile import SignerProfileResponse, map_signer_profile
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.signatures.signer_profile import MAX_PROFILE_IMAGE_BYTES, MAX_PROFILE_KEY_BYTES
from hse_doc_studio.use_cases.signer_profile.profile import (
    ClearProfileImageUC,
    ClearProfilePublicKeyUC,
    GetSignerProfileUC,
    ReadProfileImageUC,
    SaveProfileImageUC,
    SaveProfilePublicKeyUC,
)

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(require_server_mode)])

_NO_STORE = {"Cache-Control": "no-store"}


def _person() -> Actor:
    """Вошедший человек по сессии или токену."""
    actor = current_actor()
    if actor is None or not actor.id:
        raise IdentityError(IdentityErrorCode.auth_required)
    if actor.source not in (ActorSource.session, ActorSource.pat):
        raise IdentityError(IdentityErrorCode.forbidden)
    return actor


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    """Читаем на байт больше предела: сценарий сам скажет, что файл велик, а память не уйдёт на огромный файл."""
    return await file.read(limit + 1)


@router.get("/account/signer-profile", response_model=SignerProfileResponse)
async def get_signer_profile(response: Response, uc: FromDishka[GetSignerProfileUC]) -> SignerProfileResponse:
    response.headers.update(_NO_STORE)
    return map_signer_profile(await uc.execute(_person()))


@router.get("/account/signer-profile/image")
async def get_signer_profile_image(uc: FromDishka[ReadProfileImageUC]) -> Response:
    png = await uc.execute(_person())
    if png is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return Response(content=png, media_type="image/png", headers=_NO_STORE)


@router.put("/account/signer-profile/image", response_model=SignerProfileResponse)
async def save_signer_profile_image(
    uc: FromDishka[SaveProfileImageUC], file: UploadFile = File(...)
) -> SignerProfileResponse:
    try:
        profile = await uc.execute(_person(), await _read_capped(file, MAX_PROFILE_IMAGE_BYTES))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return map_signer_profile(profile)


@router.delete("/account/signer-profile/image", response_model=SignerProfileResponse)
async def clear_signer_profile_image(uc: FromDishka[ClearProfileImageUC]) -> SignerProfileResponse:
    return map_signer_profile(await uc.execute(_person()))


@router.put("/account/signer-profile/public-key", response_model=SignerProfileResponse)
async def save_signer_profile_public_key(
    uc: FromDishka[SaveProfilePublicKeyUC], file: UploadFile = File(...)
) -> SignerProfileResponse:
    """Сертификат X.509 (.cer, .crt, .pem) или открытый ключ OpenPGP (.asc); файл с закрытым ключом отвергается."""
    try:
        profile = await uc.execute(_person(), await _read_capped(file, MAX_PROFILE_KEY_BYTES))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return map_signer_profile(profile)


@router.delete("/account/signer-profile/public-key", response_model=SignerProfileResponse)
async def clear_signer_profile_public_key(uc: FromDishka[ClearProfilePublicKeyUC]) -> SignerProfileResponse:
    return map_signer_profile(await uc.execute(_person()))
