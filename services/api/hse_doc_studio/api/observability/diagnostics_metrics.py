"""Метрики самодиагностики для /metrics: статус каждой проверки, общий итог, давность и длительность."""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping

from hse_doc_studio.core.diagnostics.entities import CheckResult, DiagStatus, overall


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def diagnostics_collector(
    results: Callable[[], Mapping[str, CheckResult]],
    accepted: Callable[[], Collection[str]] = lambda: (),
) -> Callable[[], Iterable[str]]:
    def collect() -> Iterable[str]:
        found = results()
        if not found:
            return
        items = sorted(found.items())
        taken = set(accepted())
        yield "# HELP hse_diag_check_status Статус проверки: 0 ok, 1 warn, 2 fail (принятое видно как есть)."
        yield "# TYPE hse_diag_check_status gauge"
        for name, r in items:
            yield f'hse_diag_check_status{{check="{_label(name)}"}} {int(r.status)}'
        yield "# HELP hse_diag_check_accepted 1: предупреждение принято осознанно, в общий итог и оповещения не входит."
        yield "# TYPE hse_diag_check_accepted gauge"
        for name, _ in items:
            yield f'hse_diag_check_accepted{{check="{_label(name)}"}} {int(name in taken)}'
        yield "# HELP hse_diag_check_last_timestamp_seconds Когда проверка выполнялась в последний раз."
        yield "# TYPE hse_diag_check_last_timestamp_seconds gauge"
        for name, r in items:
            yield f'hse_diag_check_last_timestamp_seconds{{check="{_label(name)}"}} {int(r.checked_at.timestamp())}'
        yield "# HELP hse_diag_check_duration_seconds Длительность последней проверки."
        yield "# TYPE hse_diag_check_duration_seconds gauge"
        for name, r in items:
            yield f'hse_diag_check_duration_seconds{{check="{_label(name)}"}} {r.duration_ms / 1000:.3f}'
        yield "# HELP hse_diag_overall_status Общий итог без принятых осознанно предупреждений: 0 ok, 1 warn, 2 fail."
        yield "# TYPE hse_diag_overall_status gauge"
        yield f"hse_diag_overall_status {int(overall([r for _, r in items], taken) if items else DiagStatus.ok)}"

    return collect
