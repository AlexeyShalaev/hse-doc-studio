"""Метрики Prometheus `hse_update_*` из последнего снимка планировщика (без обращения к базе)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from hse_doc_studio.core.server_update.entities import UpdatePolicy


def update_collector(source: Callable[[], object]) -> Callable[[], Iterable[str]]:
    def collect() -> Iterable[str]:
        snap = source()
        from hse_doc_studio.use_cases.server_update.service import UpdateSnapshot  # noqa: PLC0415

        if not isinstance(snap, UpdateSnapshot):
            return []
        lines: list[str] = []

        def gauge(name: str, help_text: str, value: float | int) -> None:
            lines.extend([f"# HELP {name} {help_text}", f"# TYPE {name} gauge", f"{name} {value}"])

        gauge("hse_update_available", "Есть релиз новее установленной версии (1/0).", int(snap.available))
        gauge("hse_update_updater_up", "Апдейтер отвечает на опросы (1/0).", int(snap.updater_online))
        gauge(
            "hse_update_executor_enabled", "Обновление ставит апдейтер, не оператор (1/0).", int(snap.executor_enabled)
        )
        gauge("hse_update_run_active", "Идёт запуск обновления или отката (1/0).", int(snap.active))
        gauge(
            "hse_update_last_check_timestamp_seconds",
            "Когда фид релизов отвечал в последний раз.",
            snap.checked_at.timestamp() if snap.checked_at else 0,
        )
        for policy in UpdatePolicy:
            gauge(
                f'hse_update_policy{{policy="{policy.value}"}}',
                "Действующая политика обновления.",
                int(snap.policy is policy),
            )
        lines.extend(
            [
                "# HELP hse_update_runs_total Запусков обновления по исходу.",
                "# TYPE hse_update_runs_total counter",
            ]
        )
        lines.extend(
            f'hse_update_runs_total{{result="{status.value}"}} {n}' for status, n in sorted(snap.counts.items())
        )
        if snap.last_finished_at is not None:
            gauge(
                "hse_update_last_run_timestamp_seconds", "Конец последнего запуска.", snap.last_finished_at.timestamp()
            )
            gauge("hse_update_last_run_success", "Последний запуск удался (1/0).", int(bool(snap.last_success)))
            if snap.last_duration_s is not None:
                gauge("hse_update_last_run_duration_seconds", "Длительность последнего запуска.", snap.last_duration_s)
        return lines

    return collect
