"""Словарь вводных версии: список для панели с `affects` и числом читающих правил (раздел 2.1 дизайна результата).

Вводные строятся из схемы версии (`core/pack_studio/outcome/inputs.py`). `rules` считается по трассе на умолчаниях:
сколько решений читают вводную. `affects` это разделы, которые меняются при смене вводной. Здесь он считается по
соседним комбинациям: умолчания и каждая комбинация, где одна другая вводная сменена; этого хватает панели
(приглушить вводные, которые ничего не меняют). Точный ответ по всем комбинациям даёт атлас (срез O4).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.inputs import InputSpec, input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.model import (
    SECTIONS,
    InputInfo,
    InputsDictionary,
    InputValueInfo,
    Outcome,
    SectionName,
)
from hse_doc_studio.core.pack_studio.outcome.summary import section_prints
from hse_doc_studio.core.pack_studio.preview import PreviewExample
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve


def _reads(outcome: Outcome, input_id: str) -> int:
    """Сколько правил читают вводную: условие на ней самой или на её части (`supervisor.role`). Правило одно, сколько
    бы решений по нему ни записано (зашитое `manuals_gate` решает два руководства, но это одно правило)."""
    return len(
        {
            entry.rule
            for entry in outcome.trace
            if any(term.subject == input_id or term.subject.startswith(f"{input_id}.") for term in entry.terms)
        }
    )


def _section_prints(
    memo: dict[tuple[tuple[str, str], ...], dict[SectionName, str]],
    version: TemplateVersion,
    example: PreviewExample,
    today: date,
    combo: Mapping[str, str],
) -> dict[SectionName, str]:
    key = tuple(sorted(combo.items()))
    if key not in memo:
        outcome = resolve(version, combo, example, today, trace=False)
        memo[key] = {p.section: p.fingerprint for p in section_prints(outcome)}
    return memo[key]


def _affects(
    specs: tuple[InputSpec, ...],
    defaults: Mapping[str, str],
    version: TemplateVersion,
    example: PreviewExample,
    today: date,
) -> dict[str, tuple[SectionName, ...]]:
    memo: dict[tuple[tuple[str, str], ...], dict[SectionName, str]] = {}
    contexts: list[dict[str, str]] = [dict(defaults)]
    for other in specs:
        contexts.extend({**defaults, other.id: value} for value in other.values if value != defaults[other.id])
    result: dict[str, tuple[SectionName, ...]] = {}
    for spec in specs:
        changed: set[SectionName] = set()
        for context in contexts:
            variants = [
                _section_prints(memo, version, example, today, {**context, spec.id: value}) for value in spec.values
            ]
            changed.update(s for s in SECTIONS if len({v[s] for v in variants}) > 1)
        result[spec.id] = tuple(s for s in SECTIONS if s in changed)
    return result


def inputs_dictionary(
    version: TemplateVersion,
    example: PreviewExample,
    today: date,
    *,
    revision: str = "",
    with_affects: bool = True,
) -> InputsDictionary:
    """Вводные версии для панели.

    `with_affects=False` пропускает разбор влияния (`affects` пуст): он дороже остального."""
    specs = input_specs(version)
    defaults = normalize_inputs(specs, {}, dict(example.data.defaults) if example.data is not None else {})
    at_defaults = resolve(version, defaults, example, today)
    affects = _affects(specs, defaults, version, example, today) if with_affects else {}
    inputs = tuple(
        InputInfo(
            id=spec.id,
            group=spec.group,
            type=spec.type,
            label=dict(spec.label) if spec.label else None,
            values=tuple(InputValueInfo(value, spec.value_labels.get(value)) for value in spec.values),
            default=defaults[spec.id],
            affects=affects.get(spec.id, ()),
            rules=_reads(at_defaults, spec.id),
        )
        for spec in specs
    )
    return InputsDictionary(revision=revision, inputs=inputs, defaults=defaults)
