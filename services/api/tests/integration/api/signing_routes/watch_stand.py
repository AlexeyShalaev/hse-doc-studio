"""Сверка маршрутов на стенде: дождаться фоновых сверок, позвать хук и периодическую сверку в цикле приложения.

Хуки изменения проекта ставят сверку отдельной задачей (`RouteWatch`), а тест ходит в приложение синхронным
клиентом из другого потока. Поэтому всё, что должно выполниться в цикле приложения, идёт через его портал.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from dishka import AsyncContainer
from hse_doc_studio.core.git_remote.pdf_observer import IBuiltPdfObserver
from hse_doc_studio.use_cases.signing_route.reconcile import RouteReconciler
from hse_doc_studio.use_cases.signing_route.watch import RouteWatch

from tests.integration.api.signing_routes.signer_stand import Trio
from tests.integration.api.signing_routes.stand import Stand


def container(stand: Stand) -> AsyncContainer:
    return stand.client.app.state.dishka_container  # type: ignore[attr-defined, no-any-return]


def in_app(stand: Stand, call: Any, *args: Any) -> Any:
    portal = stand.client.portal
    assert portal is not None, "стенд работает внутри `with TestClient(...)`"
    return portal.call(call, *args)


def drain(stand: Stand) -> None:
    """Дождаться сверок, которые поставили хуки."""

    async def wait() -> None:
        watch = await container(stand).get(RouteWatch)
        for _ in range(3):
            # Хук из рабочего потока ставит задачу через цикл: дать ей появиться.
            await asyncio.sleep(0)
        await watch.drain()

    in_app(stand, wait)


def pdf_built(stand: Stand, trio: Trio, doc_id: str) -> None:
    """Хук успешной сборки документа, как его зовут хуки задачи сборки."""

    async def notify() -> None:
        (await container(stand).get(IBuiltPdfObserver)).on_pdf_built(UUID(trio.project.id), doc_id, 1)

    in_app(stand, notify)
    drain(stand)


def project_changed(stand: Stand, trio: Trio) -> None:
    """Хук изменения проекта мимо маршрута (синхронизация, восстановление из истории)."""

    async def notify() -> None:
        (await container(stand).get(RouteWatch)).on_project_changed(UUID(trio.project.id))

    in_app(stand, notify)
    drain(stand)


def sweep(stand: Stand) -> int:
    """Один проход периодической сверки; возвращает, сколько маршрутов изменилось."""

    async def run() -> int:
        async with container(stand)() as scope:
            return await (await scope.get(RouteReconciler)).sweep()

    return int(in_app(stand, run))


def notifications(stand: Stand, trio: Trio, who: str, kind: str) -> list[dict[str, Any]]:
    inbox = stand.client.get("/api/v1/account/notifications", headers=trio.people[who].headers).json()
    return [n for n in inbox["items"] if n["kind"] == kind]
