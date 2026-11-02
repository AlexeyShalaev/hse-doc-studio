"""Метрики бэкапов в формате Prometheus: возраст последнего успеха, длительность, размер, число запусков и сбоев."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from hse_doc_studio.core.backup.entities import RunStatus
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.use_cases.backup.metrics import BackupMetricsState


def backup_collector(state: BackupMetricsState, *, clock: Clock = utc_now) -> Callable[[], Iterable[str]]:
    def collect() -> Iterable[str]:
        if not state.loaded:
            return []
        ok = state.last_success
        finished = ok.finished_at if ok else None
        timestamp = finished.timestamp() if finished else 0.0
        # Успеха не было ни разу: возраст равен времени с начала эпохи, оповещение «давно нет успеха» срабатывает.
        age = max(0.0, clock().timestamp() - timestamp)
        last = state.stats.last_finished
        rows: list[tuple[str, str, str, float]] = [
            ("hse_backup_enabled", "gauge", "Расписание бэкапов включено (1) или выключено (0).", int(state.enabled)),
            ("hse_backup_running", "gauge", "Бэкап идёт сейчас.", int(state.running)),
            (
                "hse_backup_last_success_timestamp_seconds",
                "gauge",
                "Время окончания последнего успешного бэкапа (0, если успеха не было).",
                timestamp,
            ),
            (
                "hse_backup_last_success_age_seconds",
                "gauge",
                "Сколько секунд прошло с последнего успешного бэкапа (с начала эпохи, если успеха не было).",
                age,
            ),
            (
                "hse_backup_last_duration_seconds",
                "gauge",
                "Длительность последнего успешного бэкапа.",
                (ok.duration_s or 0.0) if ok else 0.0,
            ),
            (
                "hse_backup_last_size_bytes",
                "gauge",
                "Размер последнего успешного бэкапа (шифртекст всех частей).",
                (ok.size_bytes or 0) if ok else 0,
            ),
            (
                "hse_backup_failures_total",
                "counter",
                "Запусков со статусом failed за всё время (по таблице запусков, переживает перезапуск).",
                state.count(RunStatus.failed),
            ),
        ]
        if last is not None:
            rows.append(
                (
                    "hse_backup_last_run_ok",
                    "gauge",
                    "Последний завершённый запуск успешен (1) или нет (0).",
                    int(last.status is RunStatus.ok),
                )
            )
        lines: list[str] = []
        for name, kind, help_text, value in rows:
            lines += [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}", f"{name} {value}"]
        lines += [
            "# HELP hse_backup_runs_total Запусков бэкапа по статусам.",
            "# TYPE hse_backup_runs_total counter",
        ]
        lines += [f'hse_backup_runs_total{{status="{s.value}"}} {state.count(s)}' for s in RunStatus]
        return lines

    return collect
