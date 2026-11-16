"""Словарь вводных версии: список для панели с `affects` и числом читающих правил (раздел 2.1 дизайна результата).

Вводные строятся из схемы версии (`core/pack_studio/outcome/inputs.py`). `rules` считается по трассе на умолчаниях:
сколько правил читают вводную. `affects` это разделы, которые меняются при смене вводной (`impact.py`). По умолчанию
он считается по соседним комбинациям (умолчания и комбинации, где отличаются от них не больше двух вводных); этого
хватает панели (приглушить вводные, которые ничего не меняют). Точный ответ по всем комбинациям даёт атлас (срез O4):
его анализ можно передать сюда готовым (`analysis`).
"""

from __future__ import annotations

from datetime import date

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.atlas import reading_rules
from hse_doc_studio.core.pack_studio.outcome.inputs import input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.model import InputInfo, InputsDictionary, InputValueInfo, Outcome
from hse_doc_studio.core.pack_studio.preview import PreviewExample
from hse_doc_studio.use_cases.pack_studio.outcome.impact import ImpactAnalysis, OutcomeEvaluator, analyze_impact
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve


def _reads(outcome: Outcome, input_id: str) -> int:
    """Сколько правил читают вводную: условие на ней самой или на её части (`supervisor.role`). Правило одно, сколько
    бы решений по нему ни записано (зашитое `manuals_gate` решает два руководства, но это одно правило)."""
    return len(reading_rules(outcome.trace, input_id))


def inputs_dictionary(
    version: TemplateVersion,
    example: PreviewExample,
    today: date,
    *,
    revision: str = "",
    with_affects: bool = True,
    analysis: ImpactAnalysis | None = None,
) -> InputsDictionary:
    """Вводные версии для панели.

    `with_affects=False` пропускает разбор влияния (`affects` пуст): он дороже остального. По умолчанию влияние
    считается по соседним комбинациям (десятки расчётов, для панели хватает). Точное влияние по перебору даёт
    `analyze_impact` (его считает и атлас): готовый `analysis` подставляется сюда без пересчёта."""
    specs = input_specs(version)
    defaults = normalize_inputs(specs, {}, dict(example.data.defaults) if example.data is not None else {})
    at_defaults = resolve(version, defaults, example, today)
    if analysis is None and with_affects:
        analysis = analyze_impact(OutcomeEvaluator(version, specs, example, today), specs, defaults, force=False)
    affects = {input_id: impact.sections for input_id, impact in analysis.impacts.items()} if analysis else {}
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
