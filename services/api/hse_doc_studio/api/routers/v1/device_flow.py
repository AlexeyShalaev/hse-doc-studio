"""Вход устройства по коду для git сервера (раздел 7.4): `/auth/device/*` для устройства, `/account/device/*` для
человека на странице /device."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.api.rate_limit import enforce, enforce_ip
from hse_doc_studio.api.schemas.git_remote import (
    DeviceAuthorizationInfo,
    DeviceCodeRequest,
    DeviceCodeResponse,
    DeviceDecisionRequest,
    DeviceTokenRequest,
    DeviceTokenResponse,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.git_remote.device import DeviceAuthorization, DeviceClientKind
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.rate_limit import AUTH_IP, DEVICE_CODE_LOOKUP
from hse_doc_studio.use_cases.identity.device_flow import DeviceFlowService

router = APIRouter(dependencies=[Depends(require_server_mode)])
_NO_STORE = {"Cache-Control": "no-store"}


def _verification_uri() -> str:
    base = (settings.auth.public_url or "").rstrip("/")
    return f"{base}/device"


async def _service(request: Request) -> DeviceFlowService:
    service: DeviceFlowService = await request.state.dishka_container.get(DeviceFlowService)
    return service


@router.post("/auth/device/code", response_model=DeviceCodeResponse)
async def start_device_code(body: DeviceCodeRequest, request: Request) -> JSONResponse:
    await enforce_ip(request, AUTH_IP)
    started = await (await _service(request)).start(
        body.client_name, DeviceClientKind(body.client_kind), list(body.scopes), client_ip(request)
    )
    uri = _verification_uri()
    payload = DeviceCodeResponse(
        device_code=started.device_code,
        user_code=started.user_code,
        verification_uri=uri,
        verification_uri_complete=f"{uri}?code={started.user_code}",
        expires_in=started.expires_in,
        interval=started.interval,
    )
    return JSONResponse(payload.model_dump(mode="json"), headers=_NO_STORE)


@router.post("/auth/device/token", response_model=DeviceTokenResponse, responses={400: {"description": "error"}})
async def poll_device_token(body: DeviceTokenRequest, request: Request) -> JSONResponse:
    polled = await (await _service(request)).poll(body.device_code)
    if polled.error is not None or polled.access_token is None:
        error = polled.error.value if polled.error is not None else "expired_token"
        return JSONResponse({"error": error}, status_code=400, headers=_NO_STORE)
    payload = DeviceTokenResponse(
        access_token=polled.access_token,
        token_type="bearer",  # noqa: S106 — вид токена по RFC 6749, не секрет
        expires_in=polled.expires_in,
        scope=" ".join(polled.scopes),
    )
    return JSONResponse(payload.model_dump(mode="json"), headers=_NO_STORE)


def _session_actor() -> Actor:
    actor = current_actor()
    if actor is None or not actor.id:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


async def _lookup(request: Request, actor: Actor) -> DeviceFlowService:
    # Неверные коды тоже считаются: подбирать чужой код дорого и по человеку, и по адресу.
    await enforce(request, DEVICE_CODE_LOOKUP, f"user:{actor.id}")
    await enforce_ip(request, DEVICE_CODE_LOOKUP)
    return await _service(request)


def _info(item: DeviceAuthorization) -> DeviceAuthorizationInfo:
    return DeviceAuthorizationInfo(
        user_code=item.user_code,
        client_name=item.client_name,
        client_kind=item.client_kind.value,
        requested_scopes=list(item.requested_scopes),
        granted_scopes=list(item.granted_scopes) if item.granted_scopes is not None else None,
        client_ip=item.client_ip,
        requested_at=item.created_at,
        expires_at=item.expires_at,
        status=item.status.value,
    )


@router.get("/account/device/{user_code}", response_model=DeviceAuthorizationInfo)
async def get_device_authorization(user_code: str, request: Request, response: Response) -> DeviceAuthorizationInfo:
    response.headers.update(_NO_STORE)
    actor = _session_actor()
    return _info(await (await _lookup(request, actor)).info(actor, user_code))


@router.post("/account/device/{user_code}", response_model=DeviceAuthorizationInfo)
async def decide_device_authorization(
    user_code: str, body: DeviceDecisionRequest, request: Request
) -> DeviceAuthorizationInfo:
    actor = _session_actor()
    service = await _lookup(request, actor)
    return _info(await service.decide(actor, user_code, approve=body.decision == "approve", scopes=list(body.scopes)))
