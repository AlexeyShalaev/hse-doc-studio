from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from hse_doc_studio.api.schemas.signing_identity import (
    CreateSelfSignedRequest,
    SigningIdentityResponse,
    map_identity,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.signing_identities.create_self_signed import (
    CreateSelfSignedInput,
    CreateSelfSignedUC,
)
from hse_doc_studio.use_cases.signing_identities.delete_signing_identity import (
    DeleteSigningIdentityInput,
    DeleteSigningIdentityUC,
)
from hse_doc_studio.use_cases.signing_identities.import_pkcs12 import (
    ImportPkcs12Input,
    ImportPkcs12UC,
)
from hse_doc_studio.use_cases.signing_identities.list_signing_identities import (
    ListSigningIdentitiesUC,
)

router = APIRouter(route_class=DishkaRoute)


@router.get("/signing-identities", response_model=list[SigningIdentityResponse])
async def list_signing_identities(
    uc: FromDishka[ListSigningIdentitiesUC],
) -> list[SigningIdentityResponse]:
    result = await uc.execute()
    return [map_identity(i) for i in result.identities]


@router.post("/signing-identities/self-signed", response_model=SigningIdentityResponse, status_code=201)
async def create_self_signed(
    body: CreateSelfSignedRequest,
    uc: FromDishka[CreateSelfSignedUC],
) -> SigningIdentityResponse:
    try:
        result = await uc.execute(
            CreateSelfSignedInput(
                label=body.label,
                subject_cn=body.subject_cn,
                validity_days=body.validity_days,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return map_identity(result.identity)


@router.post("/signing-identities/import-pkcs12", response_model=SigningIdentityResponse, status_code=201)
async def import_pkcs12(
    uc: FromDishka[ImportPkcs12UC],
    label: str = Form(...),
    passphrase: str | None = Form(default=None),
    file: UploadFile = File(...),
) -> SigningIdentityResponse:
    content = await file.read()
    try:
        result = await uc.execute(
            ImportPkcs12Input(
                label=label,
                p12_bytes=content,
                passphrase=passphrase.encode() if passphrase else None,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return map_identity(result.identity)


@router.delete("/signing-identities/{identity_id}", status_code=204)
async def delete_signing_identity(
    identity_id: UUID,
    uc: FromDishka[DeleteSigningIdentityUC],
) -> None:
    try:
        await uc.execute(DeleteSigningIdentityInput(identity_id=identity_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
