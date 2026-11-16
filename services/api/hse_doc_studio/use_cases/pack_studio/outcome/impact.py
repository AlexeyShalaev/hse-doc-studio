"""Анализ влияния вводных на результат (раздел 4.4 дизайна результата, срез O4).

Для каждой вводной определяется, какие разделы и элементы результата она меняет. Считается по отпечаткам: берутся
комбинации вводных, в каждой группе комбинаций, где различается только эта вводная, результаты сравниваются
(`ImpactAccumulator`). Какие комбинации берутся, определяет режим:

- перебор (`exhaustive`): все комбинации, ответ точный, в том числе для влияния, которое проявляется только при
  нескольких вводных сразу. Годится, пока комбинаций не больше `EXHAUSTIVE_LIMIT` (ВКР `hse-cs-se`: 5184, около 4 с);
- соседи (`neighbors`): умолчания и комбинации, где от умолчаний отличается не больше двух вводных. Дёшево
  (десятки расчётов), для панели вводных; взаимодействие трёх вводных и больше он не видит.

Результат комбинации считает `resolve(..., trace=False)`, в память кладётся только `Snapshot` (отпечатки и хэши
элементов), а не результат целиком.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.atlas import (
    ImpactAccumulator,
    InputImpact,
    Snapshot,
    combinations_count,
    snapshot_of,
)
from hse_doc_studio.core.pack_studio.outcome.inputs import InputSpec
from hse_doc_studio.core.pack_studio.outcome.model import Digest
from hse_doc_studio.core.pack_studio.preview import PreviewExample
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve

# Предел полного перебора: больше комбинаций анализ идёт по соседям. 8192 расчёта это около 7 с на ВКР.
EXHAUSTIVE_LIMIT = 8192

type Values = tuple[str, ...]


class OutcomeEvaluator:
    """Считает и запоминает снимки результатов комбинаций одной версии и набора данных.

    Ключ комбинации это значения вводных в порядке `specs`. `check` вызывается перед каждым новым расчётом: так
    вызывающий останавливает долгий перебор по сроку. Выбросит `check`, расчёт прервётся."""

    def __init__(
        self,
        version: TemplateVersion,
        specs: Sequence[InputSpec],
        example: PreviewExample,
        today: date,
        *,
        check: Callable[[], None] | None = None,
    ) -> None:
        self._version = version
        self._example = example
        self._today = today
        self._ids = tuple(spec.id for spec in specs)
        self._check = check
        self._snapshots: dict[Values, Snapshot] = {}
        # Сжатый результат по отпечатку: у строк с одним отпечатком он один (отпечаток считается без косметики).
        self._digests: dict[str, Digest] = {}
        self.evaluated = 0

    @property
    def ids(self) -> tuple[str, ...]:
        return self._ids

    def values_of(self, combo: Mapping[str, str]) -> Values:
        return tuple(combo[input_id] for input_id in self._ids)

    def snapshot(self, values: Values) -> Snapshot:
        found = self._snapshots.get(values)
        if found is not None:
            return found
        if self._check is not None:
            self._check()
        outcome = resolve(
            self._version, dict(zip(self._ids, values, strict=True)), self._example, self._today, trace=False
        )
        snapshot = snapshot_of(outcome)
        self._snapshots[values] = snapshot
        self._digests.setdefault(snapshot.fingerprint, outcome.digest)
        self.evaluated += 1
        return snapshot

    def digest(self, fingerprint: str) -> Digest:
        return self._digests[fingerprint]

    def forget(self) -> None:
        """Освободить снимки после анализа (память растёт с числом комбинаций), сжатые результаты остаются."""
        self._snapshots.clear()


@dataclass(frozen=True, slots=True)
class ImpactAnalysis:
    """Влияние всех вводных версии: по перебору (`exact`) либо по соседним комбинациям."""

    impacts: Mapping[str, InputImpact]
    exact: bool
    combinations: int

    def sections_of(self, input_id: str) -> tuple[str, ...]:
        return self.impacts[input_id].sections


def _exhaustive(specs: Sequence[InputSpec]) -> Iterator[Values]:
    return itertools.product(*(spec.values for spec in specs))


def _neighbors(specs: Sequence[InputSpec], defaults: Mapping[str, str]) -> Iterator[Values]:
    """Умолчания и все комбинации, где от умолчаний отличаются одна или две вводные."""
    base = [defaults[spec.id] for spec in specs]
    yield tuple(base)
    others = [[v for v in spec.values if v != defaults[spec.id]] for spec in specs]
    for i, first in enumerate(others):
        for a in first:
            one = [*base]
            one[i] = a
            yield tuple(one)
            for j in range(i + 1, len(specs)):
                for b in others[j]:
                    two = [*one]
                    two[j] = b
                    yield tuple(two)


def analyze_impact(
    evaluator: OutcomeEvaluator,
    specs: Sequence[InputSpec],
    defaults: Mapping[str, str],
    *,
    exhaustive_limit: int = EXHAUSTIVE_LIMIT,
    force: bool | None = None,
) -> ImpactAnalysis:
    """Влияние каждой вводной на разделы и элементы. `force`: True перебор, False соседи, None по размеру."""
    total = combinations_count(len(spec.values) for spec in specs)
    exact = total <= exhaustive_limit if force is None else force
    combos = list(_exhaustive(specs) if exact else _neighbors(specs, defaults))
    snapshots = [evaluator.snapshot(values) for values in combos]
    impacts: dict[str, InputImpact] = {}
    for index, spec in enumerate(specs):
        accumulator = ImpactAccumulator(spec.id)
        if len(spec.values) > 1:
            first: dict[Values, Snapshot] = {}
            for values, snapshot in zip(combos, snapshots, strict=True):
                # Группа: комбинации, где все вводные кроме этой одинаковы. Хватает сравнить с первой в группе:
                # если какие-то два значения различаются, одно из них отличается от первого.
                rest = values[:index] + values[index + 1 :]
                head = first.setdefault(rest, snapshot)
                accumulator.compare(head, snapshot)
        impacts[spec.id] = accumulator.result()
    return ImpactAnalysis(impacts, exact, len(combos))
