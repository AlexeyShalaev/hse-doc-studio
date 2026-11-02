"""Долгий опрос раннера в режиме обслуживания закрывается: он не должен трогать базу во время записи восстановления."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from hse_doc_studio.api.routers.runner_api import _poll_gone


def _request(*, maintenance: object | None, disconnected: bool = False) -> Any:
    async def is_disconnected() -> bool:
        return disconnected

    state = SimpleNamespace() if maintenance is None else SimpleNamespace(maintenance=maintenance)
    return SimpleNamespace(app=SimpleNamespace(state=state), is_disconnected=is_disconnected)


async def test__poll_gone__maintenance_active__true() -> None:
    assert await _poll_gone(_request(maintenance=SimpleNamespace(active=True)))


async def test__poll_gone__maintenance_idle_and_client_connected__false() -> None:
    assert not await _poll_gone(_request(maintenance=SimpleNamespace(active=False)))


async def test__poll_gone__no_maintenance_installed__follows_client() -> None:
    assert not await _poll_gone(_request(maintenance=None))
    assert await _poll_gone(_request(maintenance=None, disconnected=True))
