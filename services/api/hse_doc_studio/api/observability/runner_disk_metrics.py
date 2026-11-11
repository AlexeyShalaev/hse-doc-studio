"""Метрики дисков раннеров для /metrics (storage-cleanup.md, 8.3): без меток по раннеру, их число не ограничено."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from hse_doc_studio.use_cases.jobs.runner_disk import RunnerDiskMetrics


def _family(name: str, kind: str, help_text: str, label: str, samples: Iterable[tuple[str, int]]) -> list[str]:
    rows = [f'{name}{{{label}="{value}"}} {number}' for value, number in samples]
    return [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}", *rows] if rows else []


def runner_disk_collector(state: RunnerDiskMetrics) -> Callable[[], Iterable[str]]:
    def collect() -> Iterable[str]:
        cleanable = state.cleanable
        if cleanable is not None:
            yield from _family(
                "hse_runner_disk_cleanable_bytes",
                "gauge",
                "Сколько можно освободить на раннерах по их последним замерам.",
                "scope",
                sorted(cleanable.items()),
            )
        yield from _family(
            "hse_runner_disk_cleanups_total",
            "counter",
            "Очисток диска раннеров по итогу.",
            "state",
            sorted(state.cleanups.items()),
        )

    return collect
