"""Ссылки доступа проекта: список, создание, правка, перевыпуск, отзыв и переходы. Гард: `SHARE`."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.schemas.admin import PageParams, page_params
from hse_doc_studio.api.schemas.sharing import (
    CreateShareLinkRequest,
    ShareLink,
    ShareLinkAuthor,
    ShareLinkList,
    ShareLinkVisit,
    ShareLinkVisitPage,
    ShareLinkVisitSummary,
    UpdateShareLinkRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.links import LinkRole
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.sharing.links import (
    CreateShareLinkUC,
    ListLinkVisitsUC,
    ListShareLinksUC,
    NewShareLink,
    RevokeShareLinkUC,
    RotateShareLinkUC,
    ShareLinkPatch,
    ShareLinkView,
    UpdateShareLinkUC,
)

router = APIRouter(dependencies=[Depends(require_server_mode)])

_NO_STORE = {"Cache-Control": "no-store"}


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def share_link_body(view: ShareLinkView) -> ShareLink:
    link = view.link
    return ShareLink(
        id=link.id,
        label=link.label,
        role=link.role.value,
        show_sources=link.show_sources,
        require_login=link.require_login,
        has_password=link.has_password,
        url=view.url,
        token_prefix=link.token_prefix,
        created_by=ShareLinkAuthor(id=view.author[0], name=view.author[1]) if view.author else None,
        created_at=link.created_at,
        updated_at=link.updated_at,
        expires_at=link.expires_at,
        state=view.state.value,
        blocked_reason=view.blocked_reason.value if view.blocked_reason else None,
        editable=view.editable,
        visits=ShareLinkVisitSummary(
            visitors=view.visits.visitors, opens=view.visits.opens, last_at=view.visits.last_at
        ),
    )


@router.get("/projects/{project_id}/links", response_model=ShareLinkList)
async def list_links(
    project_id: UUID, request: Request, response: Response, include_revoked: bool = False
) -> ShareLinkList:
    """Владелец видит все ссылки, редактор с правом делиться только свои; адрес ссылки в ответе."""
    response.headers.update(_NO_STORE)
    listing = await (await _uc(request, ListShareLinksUC)).execute(
        _actor(), project_id, include_revoked=include_revoked
    )
    return ShareLinkList(
        items=[share_link_body(v) for v in listing.items],
        can_create=listing.can_create,
        max_role=listing.max_role.value,
        forced_login=listing.forced_login,
        revoked_count=listing.revoked_count,
    )


@router.post("/projects/{project_id}/links", response_model=ShareLink, status_code=status.HTTP_201_CREATED)
async def create_link(
    project_id: UUID, body: CreateShareLinkRequest, request: Request, response: Response
) -> ShareLink:
    response.headers.update(_NO_STORE)
    new = NewShareLink(
        label=body.label,
        role=LinkRole(body.role),
        show_sources=body.show_sources,
        require_login=body.require_login,
        password=body.password,
        expires_in_days=body.expires_in_days,
    )
    view, _url = await (await _uc(request, CreateShareLinkUC)).execute(_actor(), project_id, new)
    return share_link_body(view)


@router.patch("/projects/{project_id}/links/{link_id}", response_model=ShareLink)
async def update_link(
    project_id: UUID, link_id: str, body: UpdateShareLinkRequest, request: Request, response: Response
) -> ShareLink:
    response.headers.update(_NO_STORE)
    patch = ShareLinkPatch(
        label=body.label,
        role=LinkRole(body.role) if body.role else None,
        show_sources=body.show_sources,
        require_login=body.require_login,
        password=body.password,
        clear_password=body.clear_password,
        expires_in_days=body.expires_in_days,
        clear_expiry=body.clear_expiry,
    )
    view = await (await _uc(request, UpdateShareLinkUC)).execute(_actor(), project_id, link_id, patch)
    return share_link_body(view)


@router.post("/projects/{project_id}/links/{link_id}/rotate", response_model=ShareLink)
async def rotate_link(project_id: UUID, link_id: str, request: Request, response: Response) -> ShareLink:
    response.headers.update(_NO_STORE)
    view, _url = await (await _uc(request, RotateShareLinkUC)).execute(_actor(), project_id, link_id)
    return share_link_body(view)


@router.delete("/projects/{project_id}/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_link(project_id: UUID, link_id: str, request: Request) -> Response:
    await (await _uc(request, RevokeShareLinkUC)).execute(_actor(), project_id, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/links/{link_id}/visits", response_model=ShareLinkVisitPage)
async def list_visits(
    project_id: UUID,
    link_id: str,
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
) -> ShareLinkVisitPage:
    response.headers.update(_NO_STORE)
    found = await (await _uc(request, ListLinkVisitsUC)).execute(_actor(), project_id, link_id, params.window)
    return ShareLinkVisitPage(
        items=[
            ShareLinkVisit(
                visitor_kind=v.visitor_kind, name=v.name, first_at=v.first_at, last_at=v.last_at, opens=v.opens
            )
            for v in found.items
        ],
        total=found.total,
        limit=params.limit,
        offset=params.offset,
    )
