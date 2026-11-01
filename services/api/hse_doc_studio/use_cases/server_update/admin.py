"""Входы админки в автообновление: проверка роли и делегирование сервису."""

from __future__ import annotations

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.listing import Found, Window, clamp_limit
from hse_doc_studio.core.server_update.entities import UpdateRun, UpdateSettings
from hse_doc_studio.core.server_update.status import UpdateStatus
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.server_update.service import UpdateService


class UpdateAdmin:
    def __init__(self, service: UpdateService) -> None:
        self._service = service

    async def status(self, actor: Actor) -> UpdateStatus:
        require_admin(actor)
        return await self._service.status()

    async def save_settings(self, actor: Actor, new: UpdateSettings) -> UpdateStatus:
        await self._service.update_settings(require_admin(actor), new)
        return await self._service.status()

    async def check(self, actor: Actor) -> UpdateStatus:
        return await self._service.check_now(require_admin(actor))

    async def start(self, actor: Actor, version: str | None) -> UpdateRun:
        return await self._service.request_update(require_admin(actor), version)

    async def rollback(self, actor: Actor, *, restore_db: bool) -> UpdateRun:
        return await self._service.request_rollback(require_admin(actor), restore_db=restore_db)

    async def cancel(self, actor: Actor, run_id: str) -> UpdateRun:
        return await self._service.cancel(require_admin(actor), run_id)

    async def runs(self, actor: Actor, window: Window) -> Found[UpdateRun]:
        require_admin(actor)
        return await self._service.list_runs(Window(limit=clamp_limit(window.limit), offset=max(0, window.offset)))

    async def run(self, actor: Actor, run_id: str) -> UpdateRun:
        require_admin(actor)
        return await self._service.get_run(run_id)
