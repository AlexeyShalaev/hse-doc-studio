"""Деление набора тестов на шарды CI: `pytest --shard=2/3` оставляет вторую из трёх частей.

Единица деления это файл. Файлы раскладываются жадно, самый долгий в самый лёгкий шард, по времени из
`tests/shard_durations.json`. Файлу, которого там нет, время оценивается по числу его тестов и средней
длительности теста в ближайшем каталоге с замерами. Каждый шард собирает весь набор и делит его одинаково, поэтому
части не пересекаются и вместе дают весь набор; устаревшие замеры портят только баланс, но не полноту.
Внутри шарда тесты можно раздать процессам pytest-xdist (`-n auto`): деление идёт до раздачи.

Замеры обновляются полным прогоном: `uv run pytest -n auto --no-cov --store-shard-durations`.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

DURATIONS_FILE = Path(__file__).resolve().parents[1] / "shard_durations.json"
_SHARD_RE = re.compile(r"^(\d+)/(\d+)$")
_measured: defaultdict[str, float] = defaultdict(float)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("shard", "деление набора на шарды CI")
    group.addoption(
        "--shard",
        default=None,
        metavar="K/N",
        help="оставить K-ю из N частей набора (деление по файлам, одинаковое в каждом шарде)",
    )
    group.addoption(
        "--store-shard-durations",
        action="store_true",
        default=False,
        help=f"записать время файлов этого прогона в {DURATIONS_FILE.name}",
    )


def _parse(value: str) -> tuple[int, int]:
    match = _SHARD_RE.match(value)
    if not match:
        raise pytest.UsageError(f"--shard ждёт K/N, получено {value!r}")
    index, total = int(match[1]), int(match[2])
    if not 1 <= index <= total:
        raise pytest.UsageError(f"--shard {value}: K должно быть от 1 до N")
    return index, total


def _file(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def _parents(path: str) -> list[str]:
    parts = path.split("/")[:-1]
    return ["/".join(parts[:i]) for i in range(len(parts), 0, -1)] + [""]


def estimate(counts: dict[str, int], known: dict[str, float]) -> dict[str, float]:
    """Время каждого файла: замер, а без него число тестов на среднее по ближайшему каталогу с замерами."""
    seconds: defaultdict[str, float] = defaultdict(float)
    tests: Counter[str] = Counter()
    for path, count in counts.items():
        if path in known:
            for parent in _parents(path):
                seconds[parent] += known[path]
                tests[parent] += count
    result: dict[str, float] = {}
    for path, count in counts.items():
        if path in known:
            result[path] = known[path]
            continue
        parent = next((p for p in _parents(path) if tests[p]), None)
        result[path] = count * (seconds[parent] / tests[parent] if parent is not None else 1.0)
    return result


def assign(weights: dict[str, float], total: int) -> dict[str, int]:
    """Файл -> номер шарда от 1 до total. Порядок обхода детерминирован: время по убыванию, затем путь."""
    loads = [0.0] * total
    owner: dict[str, int] = {}
    for path in sorted(weights, key=lambda p: (-weights[p], p)):
        shard = min(range(total), key=lambda i: (loads[i], i))
        loads[shard] += weights[path]
        owner[path] = shard + 1
    return owner


def _load_known() -> dict[str, float]:
    try:
        data = json.loads(DURATIONS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {str(k): float(v) for k, v in data.items()}


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    value = config.getoption("--shard")
    if value is None:
        return
    index, total = _parse(value)
    counts = Counter(_file(item.nodeid) for item in items)
    owner = assign(estimate(dict(counts), _load_known()), total)
    kept = [item for item in items if owner[_file(item.nodeid)] == index]
    deselected = [item for item in items if owner[_file(item.nodeid)] != index]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = kept


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    _measured[_file(report.nodeid)] += report.duration


def pytest_sessionfinish(session: pytest.Session) -> None:
    config = session.config
    # Под xdist отчёты всех процессов приходят в главный, там и пишем; процессы-исполнители пропускаем.
    if not config.getoption("--store-shard-durations") or hasattr(config, "workerinput") or not _measured:
        return
    root = config.rootpath
    merged = {path: secs for path, secs in _load_known().items() if (root / path).exists()}
    merged.update({path: round(secs, 2) for path, secs in _measured.items()})
    DURATIONS_FILE.write_text(json.dumps(dict(sorted(merged.items())), indent=0) + "\n", encoding="utf-8")
