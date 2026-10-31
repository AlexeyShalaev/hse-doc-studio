"""Метрики очереди и автомасштабирования в формате Prometheus: их читает внешний скейлер (например, KEDA)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from hse_doc_studio.core.jobs.autoscale import QueueMetrics, ScaleDecision


def autoscale_collector(source: Callable[[], tuple[QueueMetrics, ScaleDecision] | None]) -> Callable[[], Iterable[str]]:
    def collect() -> Iterable[str]:
        seen = source()
        if seen is None:
            return []
        metrics, decision = seen
        rows = (
            ("hse_runner_queue_depth", "Ждущих задач общего пула.", metrics.queued),
            ("hse_runner_queue_oldest_wait_seconds", "Сколько ждёт самая старая задача.", metrics.oldest_wait_s),
            ("hse_runner_jobs_running", "Идущих задач на общих раннерах.", metrics.running),
            ("hse_runners_online", "Общих раннеров в сети.", metrics.runners_online),
            ("hse_runner_slots_total", "Слотов у общих раннеров в сети.", metrics.slots_total),
            ("hse_runner_slots_busy", "Занятых слотов общих раннеров.", metrics.slots_busy),
            ("hse_autoscale_desired_runners", "Сколько раннеров хочет политика.", decision.desired),
        )
        lines: list[str] = []
        for name, help_text, value in rows:
            lines += [f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {value}"]
        return lines

    return collect
