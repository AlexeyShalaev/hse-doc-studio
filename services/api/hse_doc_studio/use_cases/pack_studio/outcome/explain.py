"""Соседние комбинации вводных для «что если» (раздел 4.6 дизайна результата).

Каждая соседняя комбинация это результат ядра `resolve` без трассы, у которого одна вводная поставлена в другое своё
значение. Расчёт дёшев (миллисекунды на комбинацию у реальных паков), но число комбинаций у версии с большим числом
анкет растёт, поэтому оно ограничено: сначала считаются вводные, которые читает хоть одно решение трассы, и расчёт
останавливается на `MAX_NEIGHBORS` комбинаций.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.explain import Neighbor, element_states, referenced_inputs
from hse_doc_studio.core.pack_studio.outcome.inputs import OutcomeInputError, input_specs
from hse_doc_studio.core.pack_studio.outcome.model import IncludeName, Outcome
from hse_doc_studio.core.pack_studio.preview import PreviewExample
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve

# Предел числа пересчётов на один ответ: у ВКР 14 соседних комбинаций, у курсового проекта 10.
MAX_NEIGHBORS = 96

# Результат, с которым сравнивают соседей, считают с этими частями, иначе у проверок «что если» не было бы ответа.
EXPLAIN_INCLUDE: frozenset[IncludeName] = frozenset({"checks"})


def neighbors_of(  # noqa: PLR0913 — версия, результат, набор, день, расчёт и предел
    version: TemplateVersion,
    base: Outcome,
    example: PreviewExample,
    today: date,
    *,
    resolver: Callable[..., Outcome] = resolve,
    limit: int = MAX_NEIGHBORS,
) -> tuple[Neighbor, ...]:
    """Соседние комбинации результата `base` (до `limit`): вводные, которые читают решения трассы, идут впереди.

    Комбинация, которую ядро отвергает (`OutcomeInputError`), пропускается; любая другая ошибка расчёта поднимается."""
    specs = input_specs(version)
    read = referenced_inputs(base.trace, {spec.id for spec in specs})
    ordered = sorted(specs, key=lambda spec: spec.id not in read)
    neighbors: list[Neighbor] = []
    for spec in ordered:
        for value in spec.values:
            if value == base.inputs.get(spec.id):
                continue
            if len(neighbors) >= limit:
                return tuple(neighbors)
            try:
                other = resolver(
                    version, {**base.inputs, spec.id: value}, example, today, include=EXPLAIN_INCLUDE, trace=False
                )
            except OutcomeInputError:
                continue
            neighbors.append(Neighbor(spec.id, value, element_states(other)))
    return tuple(neighbors)
