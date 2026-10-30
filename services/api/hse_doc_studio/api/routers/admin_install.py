"""`/api/admin/settings/instance|build`: название и адрес установки, настройки сборки.

Значения, заданные окружением, помечены в `fields` (`locked`); запись такого ключа отвечает `409 setting_locked`.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from hse_doc_studio.api.schemas.admin_install import (
    AdminBuildSettings,
    AdminInstanceSettings,
    UpdateAdminBuildRequest,
    UpdateAdminInstanceRequest,
)
from hse_doc_studio.api.schemas.session import SettingState
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.setting_source import SettingDescription
from hse_doc_studio.use_cases.admin.ops_install import (
    BuildPatch,
    BuildView,
    GetInstanceSettingsUC,
    InstancePatch,
    InstanceView,
    UpdateBuildSettingsUC,
    UpdateInstanceSettingsUC,
)

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def _fields(descriptions: dict[str, SettingDescription]) -> dict[str, SettingState]:
    return {key: SettingState(source=d.source.value, locked=d.locked) for key, d in descriptions.items()}


def _instance(view: InstanceView) -> AdminInstanceSettings:
    return AdminInstanceSettings(
        name=view.settings.name,
        public_url=view.settings.public_url,
        docs_url=view.settings.docs_url,
        fields=_fields(view.descriptions),
    )


def _build(view: BuildView) -> AdminBuildSettings:
    return AdminBuildSettings(
        timeout_s=view.settings.timeout_s,
        artifact_retention_days=view.settings.artifact_retention_days,
        personal_runners_enabled=view.personal.enabled,
        personal_runner_wait_s=view.personal.wait_s,
        personal_runners_max_per_user=view.personal.max_per_user,
        fields=_fields(view.descriptions),
    )


@router.get("/settings/instance", response_model=AdminInstanceSettings)
async def get_instance(request: Request, response: Response) -> AdminInstanceSettings:
    response.headers.update(_NO_STORE)
    return _instance(await (await _uc(request, GetInstanceSettingsUC)).instance(_actor()))


@router.put("/settings/instance", response_model=AdminInstanceSettings)
async def put_instance(body: UpdateAdminInstanceRequest, request: Request, response: Response) -> AdminInstanceSettings:
    response.headers.update(_NO_STORE)
    view = await (await _uc(request, UpdateInstanceSettingsUC)).execute(_actor(), InstancePatch(**body.model_dump()))
    return _instance(view)


@router.get("/settings/build", response_model=AdminBuildSettings)
async def get_build(request: Request, response: Response) -> AdminBuildSettings:
    response.headers.update(_NO_STORE)
    return _build(await (await _uc(request, GetInstanceSettingsUC)).build(_actor()))


@router.put("/settings/build", response_model=AdminBuildSettings)
async def put_build(body: UpdateAdminBuildRequest, request: Request, response: Response) -> AdminBuildSettings:
    response.headers.update(_NO_STORE)
    view = await (await _uc(request, UpdateBuildSettingsUC)).execute(_actor(), BuildPatch(**body.model_dump()))
    return _build(view)
