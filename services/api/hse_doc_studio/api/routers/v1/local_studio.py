"""Экран «Локальная версия» облачной Студии (docs/design/local-from-cloud.md): адрес и версия сервера, установка."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.schemas.git_remote import LocalStudioInfoResponse
from hse_doc_studio.core.git_remote.local_studio import local_studio_info

router = APIRouter(dependencies=[Depends(require_server_mode)])


def _server_url(request: Request) -> str:
    """Адрес, который увидит локальная Студия: внешний `public_url`, без него адрес этого запроса."""
    public = (settings.auth.public_url or "").strip()
    return public or str(request.base_url)


@router.get("/local-studio", response_model=LocalStudioInfoResponse)
async def get_local_studio_info(request: Request) -> LocalStudioInfoResponse:
    info = local_studio_info(
        server_url=_server_url(request),
        server_version=settings.get_app_version(),
        github_repo=settings.github_repo,
        git_remote_enabled=settings.git_remote.enabled,
    )
    return LocalStudioInfoResponse(
        server_url=info.server_url,
        server_version=info.server_version,
        git_remote_enabled=info.git_remote_enabled,
        recommended_tag=info.recommended_tag,
        image=info.image,
        install_base_url=info.install_base_url,
        releases_url=info.releases_url,
        default_port=info.default_port,
    )
