from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.schemas.signing_identity import (
    CreateSelfSignedRequest,
    GenerateOpenPgpKeyRequest,
    ImportOpenPgpKeyResponse,
    OpenPgpKeysResponse,
    SigningIdentityResponse,
    TrustedRootResponse,
    map_identity,
    map_openpgp_key,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.infra.signatures.chain_fetcher import ChainFetcher
from hse_doc_studio.infra.signatures.trusted_roots import TrustedRoot, TrustedRootStore
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
from hse_doc_studio.use_cases.signing_identities.openpgp_keys import (
    CreateOpenPgpKeyInput,
    CreateOpenPgpKeyUC,
    ExportOpenPgpPublicKeyInput,
    ExportOpenPgpPublicKeyUC,
    ImportOpenPgpKeyInput,
    ImportOpenPgpKeyUC,
    ListOpenPgpKeysUC,
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


@router.post("/signing-identities/openpgp/generate", response_model=SigningIdentityResponse, status_code=201)
async def generate_openpgp_key(
    body: GenerateOpenPgpKeyRequest,
    uc: FromDishka[CreateOpenPgpKeyUC],
) -> SigningIdentityResponse:
    try:
        result = await uc.execute(
            CreateOpenPgpKeyInput(name=body.name, email=body.email, label=body.label, passphrase=body.passphrase)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return map_identity(result.identity)


@router.post("/signing-identities/openpgp/import", response_model=ImportOpenPgpKeyResponse, status_code=201)
async def import_openpgp_key(
    uc: FromDishka[ImportOpenPgpKeyUC],
    label: str = Form(default=""),
    passphrase: str = Form(default=""),
    file: UploadFile = File(...),
) -> ImportOpenPgpKeyResponse:
    content = await file.read()
    try:
        result = await uc.execute(ImportOpenPgpKeyInput(data=content, passphrase=passphrase, label=label))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportOpenPgpKeyResponse(
        identities=[map_identity(i) for i in result.identities],
        public_keys=[map_openpgp_key(k) for k in result.public_keys],
    )


@router.get("/signing-identities/openpgp/keys", response_model=OpenPgpKeysResponse)
async def list_openpgp_keys(uc: FromDishka[ListOpenPgpKeysUC]) -> OpenPgpKeysResponse:
    result = await uc.execute()
    return OpenPgpKeysResponse(
        available=result.gpg_version is not None,
        gpg_version=result.gpg_version,
        keys=[map_openpgp_key(k) for k in result.keys],
    )


@router.get("/signing-identities/{identity_id}/public-key")
async def export_openpgp_public_key(
    identity_id: UUID,
    uc: FromDishka[ExportOpenPgpPublicKeyUC],
) -> Response:
    try:
        result = await uc.execute(ExportOpenPgpPublicKeyInput(identity_id=identity_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=result.armored,
        media_type="application/pgp-keys",
        headers={"Content-Disposition": f'attachment; filename="{result.file_name}"'},
    )


@router.get("/crypto/cadesplugin_api.js")
async def get_cadesplugin_api() -> FileResponse:
    """The CryptoPro plug-in loader, when the user put a copy into <data>/cadesplugin/ (offline use)."""
    path = settings.data_dir.expanduser() / "cadesplugin" / "cadesplugin_api.js"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="cadesplugin_api.js not installed")
    return FileResponse(path, media_type="application/javascript")


def _map_root(root: TrustedRoot) -> TrustedRootResponse:
    return TrustedRootResponse(
        fingerprint=root.fingerprint, subject=root.subject, not_before=root.not_before, not_after=root.not_after
    )


@router.get("/trusted-roots", response_model=list[TrustedRootResponse])
async def list_trusted_roots(store: FromDishka[TrustedRootStore]) -> list[TrustedRootResponse]:
    return [_map_root(r) for r in store.list_all()]


@router.post("/trusted-roots", response_model=TrustedRootResponse, status_code=201)
async def add_trusted_root(store: FromDishka[TrustedRootStore], file: UploadFile = File(...)) -> TrustedRootResponse:
    try:
        return _map_root(store.add(await file.read()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/trusted-roots/from-chain/{fingerprint}", response_model=TrustedRootResponse, status_code=201)
async def trust_root_from_chain(
    fingerprint: str,
    store: FromDishka[TrustedRootStore],
    fetcher: FromDishka[ChainFetcher],
) -> TrustedRootResponse:
    """Trust a root the Studio fetched while completing a signature's chain (the user confirmed its SHA-256)."""
    blob = fetcher.load(fingerprint)
    if blob is None:
        raise HTTPException(status_code=404, detail="certificate not found among the fetched ones")
    try:
        return _map_root(store.add(blob))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/trusted-roots/{fingerprint}", status_code=204)
async def delete_trusted_root(fingerprint: str, store: FromDishka[TrustedRootStore]) -> None:
    try:
        store.delete(fingerprint)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
