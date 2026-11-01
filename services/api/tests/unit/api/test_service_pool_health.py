from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from hse_doc_studio.api.observability.health import HealthRegistry
from hse_doc_studio.api.observability.install import install_service_pool_health


class _Container:
    def __init__(self, items: dict[str, Any]) -> None:
        self._items = items

    async def get(self, kind: type) -> Any:
        return self._items[kind.__name__]


class _Proxy:
    def __init__(self, healthy: bool) -> None:
        self._healthy = healthy

    async def probe(self) -> bool:
        return self._healthy


class _Editor:
    def __init__(self, url: str | None) -> None:
        self._url = url

    async def ensure_running(self) -> str | None:
        return self._url


def _cfg(lt: list[str], office: list[str]) -> Any:
    return SimpleNamespace(
        languagetool=SimpleNamespace(pool_replicas=lt), office_editor=SimpleNamespace(pool_replicas=office)
    )


async def test__no_replicas__nothing_registered() -> None:
    health = HealthRegistry()

    install_service_pool_health(FastAPI(), _Container({}), health, _cfg([], []))  # type: ignore[arg-type]

    assert health.probes == {}


async def test__replicas_configured__probes_report_reason_and_stay_optional() -> None:
    health = HealthRegistry()
    container = _Container({"LanguageToolProxy": _Proxy(False), "IOfficeEditorService": _Editor("http://oo")})

    install_service_pool_health(
        FastAPI(),
        container,  # type: ignore[arg-type]
        health,
        _cfg(["http://lt"], ["http://oo"]),
    )

    assert await health.run() == {"languagetool": "no_healthy_replica", "onlyoffice": None}
    assert health.optional == {"languagetool", "onlyoffice"}
