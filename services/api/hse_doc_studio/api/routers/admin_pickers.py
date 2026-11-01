"""`/api/admin/pickers/*`: поиск человека или организации для полей выбора админки.

Пикер не листается: первые `limit` (до 20) подходящих по имени и `has_more`, если стоит уточнить поиск.
Пикеры живут под гардом админки: их видит только админ установки, остальным 404, как у прочих ручек.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from hse_doc_studio.api.schemas.admin import PickerItem, PickerList, PickerParams, picker_params
from hse_doc_studio.api.schemas.session import AccountStatus
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import UserPickQuery, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.admin.orgs import PickOrgsUC
from hse_doc_studio.use_cases.admin.users import PickUsersUC

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


@router.get("/pickers/users", response_model=PickerList)
async def pick_users(
    request: Request,
    response: Response,
    params: Annotated[PickerParams, Depends(picker_params)],
    account_status: Annotated[AccountStatus | None, Query(alias="status")] = None,
    not_in_org: Annotated[str | None, Query(max_length=64, description="Не состоит в организации (slug)")] = None,
    not_in_group: Annotated[str | None, Query(max_length=64, description="Не состоит в группе (id)")] = None,
) -> PickerList:
    response.headers.update(_NO_STORE)
    query = UserPickQuery(
        q=params.q,
        limit=params.limit,
        status=UserStatus(account_status) if account_status else None,
        not_in_org_slug=not_in_org,
        not_in_group_id=not_in_group,
    )
    found = await (await request.state.dishka_container.get(PickUsersUC)).execute(_actor(), query)
    return PickerList(
        items=[PickerItem(kind="user", id=u.id, name=u.name, detail=u.email) for u in found.items],
        has_more=found.has_more,
    )


@router.get("/pickers/orgs", response_model=PickerList)
async def pick_orgs(
    request: Request, response: Response, params: Annotated[PickerParams, Depends(picker_params)]
) -> PickerList:
    response.headers.update(_NO_STORE)
    found = await (await request.state.dishka_container.get(PickOrgsUC)).execute(_actor(), params.q, params.limit)
    # id организации наружу не отдаётся: в админ-API её адресует slug.
    return PickerList(
        items=[PickerItem(kind="org", id=o.slug, name=o.name, detail=o.slug) for o in found.items],
        has_more=found.has_more,
    )
