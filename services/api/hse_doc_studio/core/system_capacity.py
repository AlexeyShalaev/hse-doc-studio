"""Ресурсы машины и производные от них значения настроек по умолчанию.

Дефолты «2 одновременные сборки» и «предупреждать при 10 ГБ» были константами,
одинаковыми для ноутбука с 4 ядрами и для рабочей станции с 24: на слабой машине
две сборки уже мешают работать, на сильной — простаивают 20 ядер, а порог диска в
10 ГБ на терабайтном диске срабатывает практически сразу (один образ TeX Live
весит ~9 ГБ). Поэтому дефолты считаются от реальных лимитов машины, а пользователь
по-прежнему может выставить своё значение в Настройках — сохранённое всегда главнее.

Формулы живут в домене (чистые функции от снимка ресурсов) и потому проверяются
тестами без докера, psutil и файловой системы.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Одна сборка = один texlive-контейнер: latexmk внутри однопоточный, поэтому
# считаем по ядрам, но оставляем половину машины пользователю — инструмент
# локальный, и «собрать всё» не должно вешать ноутбук.
CORES_PER_COMPILE = 2
# Пиковый xelatex на большом документе — сотни МБ; 2 ГБ на слот дают запас и не
# дают уйти в своп на машине с малой памятью.
RAM_GB_PER_COMPILE = 2
# Шаги переключателя «Одновременных сборок» в Настройках. Дефолт обязан попадать
# ровно в один из них, иначе в UI не подсветится ни одна кнопка и пользователь
# увидит переключатель без выбранного значения. По возрастанию.
CONCURRENCY_STEPS = (1, 2, 3, 4, 6, 8)
# Потолок совпадает с валидацией API и максимумом в UI (Настройки → Компилятор).
MAX_CONCURRENT_COMPILES_CEILING = CONCURRENCY_STEPS[-1]
MIN_CONCURRENT_COMPILES = CONCURRENCY_STEPS[0]
# Значение для машины, о которой не удалось узнать ничего: прежняя константа.
FALLBACK_CONCURRENT_COMPILES = 2

# Доля диска, после которой мусор докера стоит показать пользователю.
DISK_WARN_SHARE = 0.05
# Шаги переключателя порога (0 = «не предупреждать» — выбор пользователя, а не дефолт).
DISK_WARN_STEPS_GB = (5, 10, 20, 50)
MIN_DISK_WARN_GB = DISK_WARN_STEPS_GB[0]
MAX_DISK_WARN_GB = DISK_WARN_STEPS_GB[-1]
FALLBACK_DISK_WARN_GB = 10

_MB_PER_GB = 1024
_BYTES_PER_GB = 1024**3


def _snap_down(value: float, steps: tuple[int, ...]) -> int:
    """Ближайший шаг НЕ ВЫШЕ значения (ниже первого шага — сам первый шаг)."""
    allowed = [s for s in steps if s <= value]
    return allowed[-1] if allowed else steps[0]


@dataclass(frozen=True)
class SystemCapacity:
    """Снимок ресурсов машины. Любое поле — None, если определить не удалось."""

    cpu_count: int | None = None
    total_ram_mb: int | None = None
    # Полный объём диска, на котором лежат данные приложения (в контейнере — того
    # же, где докер держит образы), в байтах.
    disk_total_bytes: int | None = None


class ISystemCapacityProbe(Protocol):
    """Определяет ресурсы машины. Реализуется в infra; НИКОГДА не бросает."""

    def detect(self) -> SystemCapacity: ...


def default_max_concurrent_compiles(capacity: SystemCapacity) -> int:
    """Сколько сборок гонять параллельно на этой машине по умолчанию."""
    limits = []
    if capacity.cpu_count:
        limits.append(capacity.cpu_count // CORES_PER_COMPILE)
    if capacity.total_ram_mb:
        limits.append(capacity.total_ram_mb // _MB_PER_GB // RAM_GB_PER_COMPILE)
    if not limits:
        return FALLBACK_CONCURRENT_COMPILES
    # Узкое место — тот ресурс, которого меньше.
    return _snap_down(min(*limits, MAX_CONCURRENT_COMPILES_CEILING), CONCURRENCY_STEPS)


def default_disk_usage_warn_gb(capacity: SystemCapacity) -> int:
    """Порог (ГБ) освобождаемого места, после которого предупреждать о мусоре докера."""
    if not capacity.disk_total_bytes:
        return FALLBACK_DISK_WARN_GB
    share_gb = capacity.disk_total_bytes * DISK_WARN_SHARE / _BYTES_PER_GB
    return _snap_down(share_gb, DISK_WARN_STEPS_GB)


def capacity_scaled_defaults(capacity: SystemCapacity) -> dict[str, int]:
    """Настройки, дефолт которых зависит от машины (ключи — как в config.json)."""
    return {
        "max_concurrent_compiles": default_max_concurrent_compiles(capacity),
        "disk_usage_warn_gb": default_disk_usage_warn_gb(capacity),
    }
