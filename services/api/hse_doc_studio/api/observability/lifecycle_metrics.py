"""Метрики жизненного цикла данных для /metrics: размеры источников, итоги очистки, место на томах, безопасный режим."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping

from hse_doc_studio.core.lifecycle.disk import SafeMode
from hse_doc_studio.core.lifecycle.ports import VolumeUsage
from hse_doc_studio.use_cases.lifecycle.engine import ProcessCounters


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _family(name: str, kind: str, help_text: str, samples: Iterable[tuple[str, str, float | int]]) -> list[str]:
    """Семейство метрик: HELP/TYPE и строки `name{label="значение"} число`; пустое семейство не печатается."""
    rows = [f'{name}{{{label}="{_label(value)}"}} {number}' for label, value, number in samples]
    return [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}", *rows] if rows else []


def _source_families(seen: Mapping[str, ProcessCounters]) -> list[str]:
    items = sorted(seen.items())
    sized = [(k, c.size) for k, c in items if c.size is not None]
    out = _family(
        "hse_lifecycle_source_bytes",
        "gauge",
        "Размер источника роста данных.",
        [("source", k, s.bytes) for k, s in sized],
    )
    out += _family(
        "hse_lifecycle_source_rows",
        "gauge",
        "Оценка числа строк источника.",
        [("source", k, s.rows) for k, s in sized if s.rows is not None],
    )
    for name, kind, help_text, pick in (
        ("hse_lifecycle_removed_total", "counter", "Удалено строк и файлов очисткой.", lambda c: c.removed),
        (
            "hse_lifecycle_partitions_dropped_total",
            "counter",
            "Отброшено партиций вместо DELETE.",
            lambda c: c.partitions_dropped,
        ),
        ("hse_lifecycle_errors_total", "counter", "Прогонов очистки с ошибкой.", lambda c: c.errors),
    ):
        out += _family(name, kind, help_text, [("source", k, pick(c)) for k, c in items])
    out += _family(
        "hse_lifecycle_last_run_timestamp_seconds",
        "gauge",
        "Когда источник чистили в последний раз.",
        [("source", k, int(c.last_run_ts)) for k, c in items if c.last_run_ts],
    )
    return out


def _volume_families(found: list[VolumeUsage]) -> list[str]:
    out = _family(
        "hse_storage_used_bytes",
        "gauge",
        "Занято на томе (для базы размер базы).",
        [("volume", v.name, v.used_bytes) for v in found],
    )
    out += _family(
        "hse_storage_total_bytes",
        "gauge",
        "Ёмкость тома.",
        [("volume", v.name, v.total_bytes) for v in found if v.total_bytes is not None],
    )
    out += _family(
        "hse_storage_used_ratio",
        "gauge",
        "Доля занятого места на томе от 0 до 1.",
        [("volume", v.name, round(v.used_ratio, 4)) for v in found if v.used_ratio is not None],
    )
    return out


def lifecycle_collector(
    counters: Callable[[], Mapping[str, ProcessCounters]],
    volumes: Callable[[], list[VolumeUsage]],
    safe_mode: SafeMode,
) -> Callable[[], Iterable[str]]:
    def collect() -> Iterable[str]:
        yield from _source_families(counters())
        yield from _volume_families(volumes())
        yield "# HELP hse_storage_safe_mode 1, если места критически мало и крупные загрузки отклоняются."
        yield "# TYPE hse_storage_safe_mode gauge"
        yield f"hse_storage_safe_mode {int(safe_mode.active)}"

    return collect
