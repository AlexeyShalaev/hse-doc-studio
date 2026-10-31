"""Страница ссылки доступа и гостевая сессия: превью, открытие, имя гостя и выход из гостевого режима.

`GET /links/{token}` и `POST /links/{token}/open` публичные: актора по cookie гард не ставит, поэтому вошедшего
человека маршрут определяет сам (сессия или PAT со scope `api`). Несуществующая, отозванная и истёкшая
ссылки отвечают одинаково (`inactive` в превью, 404 `link_inactive` при открытии).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.auth_cookie import (
    clear_guest_cookie,
    credentials_from_request,
    is_secure_public_url,
    set_guest_cookie,
)
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.api.rate_limit import enforce, enforce_ip
from hse_doc_studio.api.schemas.sharing import (
    GuestInfo,
    GuestLinkInfo,
    OpenShareLinkRequest,
    OpenShareLinkResponse,
    ShareLinkPreview,
    UpdateGuestSessionRequest,
)
from hse_doc_studio.core.access.entities import Actor, ActorKind, ActorSource
from hse_doc_studio.core.access.links import GuestSession, hash_secret
from hse_doc_studio.core.identity.entities import TokenScope
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.rate_limit import LINK_IP, LINK_TOKEN
from hse_doc_studio.use_cases.sharing.open_link import (
    GuestInfoUC,
    GuestInfoView,
    GuestSessionService,
    LeaveGuestSessionUC,
    OpenRequest,
    OpenShareLinkUC,
    PreviewShareLinkUC,
    UpdateGuestSessionUC,
)

router = APIRouter(dependencies=[Depends(require_server_mode)])

_NO_STORE = {"Cache-Control": "no-store"}


async def _uc[T](request: Request, kind: type[T]) -> T:
    container = getattr(request.state, "dishka_container", None) or request.app.state.dishka_container
    return await container.get(kind)


async def _signed_in(request: Request) -> Actor | None:
    """Вошедший человек (сессия или PAT со scope `api`); гость и аноним дают None."""
    container = getattr(request.state, "dishka_container", None) or request.app.state.dishka_container
    resolver = await container.get(IActorResolver)
    actor = await resolver.resolve(credentials_from_request(request))
    if actor is None or actor.kind is not ActorKind.user:
        return None
    if actor.source is ActorSource.pat and TokenScope.api.value not in actor.scopes:
        return None
    return actor


async def _guest_session(request: Request) -> GuestSession | None:
    secret = credentials_from_request(request).guest_secret
    if not secret:
        return None
    return await (await _uc(request, GuestSessionService)).resolve(secret)


def _secure() -> bool:
    return is_secure_public_url(settings.auth.public_url)


def guest_info_body(view: GuestInfoView) -> GuestInfo:
    return GuestInfo(
        name=view.name,
        links=[
            GuestLinkInfo(
                project_id=x.project_id,
                project_name=x.project_name,
                link_label=x.link_label,
                role=x.role.value,
                show_sources=x.show_sources,
            )
            for x in view.links
        ],
    )


async def guest_bootstrap(request: Request) -> tuple[GuestInfo | None, str | None]:
    """Блок `guest` и CSRF-токен гостевой сессии для bootstrap; без гостевой cookie оба None."""
    session = await _guest_session(request)
    if session is None:
        return None, None
    view = await (await _uc(request, GuestInfoUC)).execute(session)
    return guest_info_body(view), session.csrf_token


@router.get("/links/{token}", response_model=ShareLinkPreview)
async def preview_link(token: str, request: Request, response: Response) -> ShareLinkPreview:
    response.headers.update(_NO_STORE)
    await enforce_ip(request, LINK_IP)
    preview = await (await _uc(request, PreviewShareLinkUC)).execute(token, await _signed_in(request))
    return ShareLinkPreview(
        state=preview.state.value,
        project_name=preview.project_name,
        owner_name=preview.owner_name,
        role=preview.role.value if preview.role else None,
        show_sources=preview.show_sources,
        guest_name_required=preview.guest_name_required,
        signed_in=preview.signed_in,
    )


@router.post("/links/{token}/open", response_model=OpenShareLinkResponse)
async def open_link(
    token: str, body: OpenShareLinkRequest, request: Request, response: Response
) -> OpenShareLinkResponse:
    response.headers.update(_NO_STORE)
    await enforce_ip(request, LINK_IP)
    # Все гости одной ссылки вместе: ключ по хешу токена, сам токен в счётчики не попадает.
    await enforce(request, LINK_TOKEN, f"link:{hash_secret(token)}")
    actor = await _signed_in(request)
    guests = await _uc(request, GuestSessionService)
    opened = await (await _uc(request, OpenShareLinkUC)).execute(
        OpenRequest(
            token=token,
            password=body.password,
            guest_name=body.guest_name,
            actor=actor,
            guest=None if actor is not None else await _guest_session(request),
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )
    )
    if opened.guest_secret is not None:
        set_guest_cookie(
            response, opened.guest_secret, secure=_secure(), max_age_s=int(guests.lifetime.total_seconds())
        )
    return OpenShareLinkResponse(
        project_id=opened.project_id,
        mode=opened.mode,
        role=opened.role.value,
        show_sources=opened.show_sources,
        landing=opened.landing,
    )


@router.patch("/links/session", response_model=GuestInfo)
async def rename_guest(body: UpdateGuestSessionRequest, request: Request, response: Response) -> GuestInfo:
    response.headers.update(_NO_STORE)
    session = await _guest_session(request)
    if session is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    view = await (await _uc(request, UpdateGuestSessionUC)).execute(session, body.name)
    return guest_info_body(view)


@router.delete("/links/session", status_code=status.HTTP_204_NO_CONTENT)
async def leave_guest(request: Request) -> Response:
    session = await _guest_session(request)
    if session is not None:
        await (await _uc(request, LeaveGuestSessionUC)).execute(session)
    result = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_guest_cookie(result, secure=_secure())
    return result
