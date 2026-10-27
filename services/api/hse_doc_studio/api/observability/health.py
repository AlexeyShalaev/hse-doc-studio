"""Живость и готовность: публично только ok/fail, детали по токену или админу."""

from __future__ import annotations

import asyncio
import hmac
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

from hse_doc_studio.api.observability.metrics import MetricsRegistry

HealthProbe = Callable[[], Awaitable[str | None]]
Privilege = Callable[[Request], Awaitable[bool]]
_PROBE_TIMEOUT_S = 3.0


@dataclass
class HealthRegistry:
    """Проверки готовности: имя -> корутина, возвращающая None (здорово) или причину."""

    probes: dict[str, HealthProbe] = field(default_factory=dict)

    def register(self, name: str, probe: HealthProbe) -> None:
        if name in self.probes:
            msg = f"проверка здоровья {name} уже зарегистрирована"
            raise ValueError(msg)
        self.probes[name] = probe

    async def run(self) -> dict[str, str | None]:
        async def one(probe: HealthProbe) -> str | None:
            try:
                return await asyncio.wait_for(probe(), timeout=_PROBE_TIMEOUT_S)
            except TimeoutError:
                return "timeout"
            except Exception as exc:
                return f"{type(exc).__name__}"

        names = list(self.probes)
        results = await asyncio.gather(*(one(self.probes[n]) for n in names))
        return dict(zip(names, results, strict=True))


def bearer_matches(request: Request, token: str | None) -> bool:
    if not token:
        return False
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    # заголовок Starlette декодирует как latin-1: сравниваем байты, иначе не-ASCII даёт TypeError
    return scheme.lower() == "bearer" and hmac.compare_digest(
        value.strip().encode("utf-8", "surrogatepass"), token.encode("utf-8", "surrogatepass")
    )


def build_health_router(
    registry: HealthRegistry,
    *,
    health_token: str | None = None,
    is_privileged: Privilege | None = None,
) -> APIRouter:
    """``is_privileged`` подключает проверку админа установки, когда появится identity."""
    router = APIRouter(tags=["health"], include_in_schema=False)

    async def privileged(request: Request) -> bool:
        if bearer_matches(request, health_token):
            return True
        return is_privileged is not None and await is_privileged(request)

    @router.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/health/ready")
    async def ready(request: Request) -> JSONResponse:
        results = await registry.run()
        ok = all(reason is None for reason in results.values())
        body: dict[str, object] = {"status": "ok" if ok else "fail"}
        if await privileged(request):
            body["checks"] = {name: {"ok": reason is None, "reason": reason} for name, reason in results.items()}
        return JSONResponse(body, status_code=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE)

    return router


def build_metrics_router(registry: MetricsRegistry, *, metrics_token: str | None) -> APIRouter:
    router = APIRouter(tags=["metrics"], include_in_schema=False)

    @router.get("/metrics")
    async def metrics(request: Request) -> PlainTextResponse:
        if not bearer_matches(request, metrics_token):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return PlainTextResponse(registry.render(), media_type="text/plain; version=0.0.4")

    return router
