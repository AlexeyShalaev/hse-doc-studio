"""Минимальные метрики в текстовом формате Prometheus без внешних зависимостей."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from threading import Lock

from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_Labels = tuple[str, str, str]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._count: dict[_Labels, int] = defaultdict(int)
        self._sum: dict[_Labels, float] = defaultdict(float)
        self._buckets: dict[_Labels, list[int]] = defaultdict(lambda: [0] * len(_BUCKETS))
        self._in_flight = 0
        self._collectors: list[Callable[[], Iterable[str]]] = []

    def add_collector(self, collector: Callable[[], Iterable[str]]) -> None:
        """Источник готовых строк экспозиции (метрики фоновых задач и других зон)."""
        self._collectors.append(collector)

    def request_started(self) -> None:
        with self._lock:
            self._in_flight += 1

    def request_finished(self, method: str, route: str, status: int, seconds: float) -> None:
        key = (method, route, f"{status // 100}xx")
        with self._lock:
            self._in_flight -= 1
            self._count[key] += 1
            self._sum[key] += seconds
            buckets = self._buckets[key]
            for i, bound in enumerate(_BUCKETS):
                if seconds <= bound:
                    buckets[i] += 1

    def render(self) -> str:
        lines = [
            "# HELP hse_http_requests_total HTTP-запросы по методу, маршруту и классу статуса.",
            "# TYPE hse_http_requests_total counter",
        ]
        with self._lock:
            count, total, buckets, in_flight = dict(self._count), dict(self._sum), dict(self._buckets), self._in_flight
        for (method, route, cls), value in sorted(count.items()):
            lines.append(
                f'hse_http_requests_total{{method="{method}",route="{_escape(route)}",status="{cls}"}} {value}'
            )
        lines += [
            "# HELP hse_http_request_duration_seconds Длительность HTTP-запросов.",
            "# TYPE hse_http_request_duration_seconds histogram",
        ]
        for key in sorted(count):
            method, route, cls = key
            base = f'method="{method}",route="{_escape(route)}",status="{cls}"'
            for bound, hits in zip(_BUCKETS, buckets[key], strict=True):
                lines.append(f'hse_http_request_duration_seconds_bucket{{{base},le="{bound}"}} {hits}')
            lines.append(f'hse_http_request_duration_seconds_bucket{{{base},le="+Inf"}} {count[key]}')
            lines.append(f"hse_http_request_duration_seconds_sum{{{base}}} {total[key]:.6f}")
            lines.append(f"hse_http_request_duration_seconds_count{{{base}}} {count[key]}")
        lines += ["# TYPE hse_http_requests_in_flight gauge", f"hse_http_requests_in_flight {in_flight}"]
        for collector in self._collectors:
            lines.extend(collector())
        return "\n".join(lines) + "\n"


def background_collector(runner: object) -> Callable[[], Iterable[str]]:
    """Метрики BackgroundTaskRunner: лидерство и длительность прогонов по задачам."""

    def collect() -> Iterable[str]:
        stats = runner.stats()  # type: ignore[attr-defined]
        yield "# TYPE hse_background_leader gauge"
        yield f"hse_background_leader {int(runner.is_leader)}"  # type: ignore[attr-defined]
        yield "# TYPE hse_background_task_runs_total counter"
        for name, st in sorted(stats.items()):
            yield f'hse_background_task_runs_total{{task="{_escape(name)}"}} {st.runs}'
        yield "# TYPE hse_background_task_failures_total counter"
        for name, st in sorted(stats.items()):
            yield f'hse_background_task_failures_total{{task="{_escape(name)}"}} {st.failures}'
        yield "# TYPE hse_background_task_duration_seconds gauge"
        for name, st in sorted(stats.items()):
            yield f'hse_background_task_duration_seconds{{task="{_escape(name)}"}} {st.last_duration_s:.6f}'

    return collect


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, registry: MetricsRegistry) -> None:
        self.app = app
        self._registry = registry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        status = 500
        started = time.perf_counter()
        self._registry.request_started()

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            self._registry.request_finished(
                scope["method"], self._route_template(scope), status, time.perf_counter() - started
            )

    @staticmethod
    def _route_template(scope: Scope) -> str:
        """Шаблон маршрута, а не путь: id проектов не должны плодить серии метрик."""
        app = scope.get("app")
        for route in getattr(app, "routes", []):
            match, _ = route.matches(scope)
            if match is Match.FULL:
                return str(getattr(route, "path", "unknown"))
        return "unmatched"
