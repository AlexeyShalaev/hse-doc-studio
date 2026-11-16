"""Атлас результата версии: измерения, таблица исходов, группы одинаковых исходов (раздел 4.4 дизайна результата).

1. Влияние (`impact.py`): измерения это вводные, смена значения которых меняет отпечаток хотя бы одного раздела.
   Считается перебором всех комбинаций, если их не больше 2048, иначе по соседним комбинациям силы 3 (у ВКР
   `hse-cs-se` 5184 комбинации, 418 расчётов). Остальные вводные в `ignored`: `no_effect` или `cosmetic` (меняют
   только имена файлов, язык редакции и доступность вариантов, R12).
2. Таблица: произведение значений измерений при остальных вводных на умолчаниях набора данных, строка `{key, outcome}`.
3. Исходы: уникальные отпечатки с `digest` и числом строк. Клиент по ключу находит исход и сразу рисует результат.

`pin` закрепляет вводную на одном значении и режет таблицу: закреплённая вводная остаётся измерением с одним значением,
чтобы ключ строки не менял форму. Больше `limit` строк это `AtlasTooLarge`. Анализ влияния от `pin` не зависит, поэтому
вызывающий может передать готовый (`analysis`) и пересчитывать только таблицу.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.atlas import (
    ATLAS_MAX_ROWS,
    MAX_DIMENSION_RULES,
    Atlas,
    AtlasDimension,
    AtlasIgnored,
    assemble_table,
    combinations_count,
    reading_rules,
)
from hse_doc_studio.core.pack_studio.outcome.inputs import InputSpec, OutcomeInputError, input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.model import Digest, RuleRef
from hse_doc_studio.core.pack_studio.preview import PreviewExample
from hse_doc_studio.use_cases.pack_studio.outcome.impact import (
    EXHAUSTIVE_LIMIT,
    ImpactAnalysis,
    OutcomeEvaluator,
    analyze_impact,
)
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve


def example_defaults(example: PreviewExample) -> dict[str, str]:
    return dict(example.data.defaults) if example.data is not None else {}


def validate_pins(specs: Sequence[InputSpec], pins: Mapping[str, str]) -> None:
    """Закреплена незнакомая вводная или значение вне списка: `OutcomeInputError` (на границе `inputs_invalid`)."""
    known = {spec.id: spec for spec in specs}
    for input_id, value in pins.items():
        spec = known.get(input_id)
        if spec is None:
            raise OutcomeInputError(input_id, value, "unknown input")
        if value not in spec.values:
            raise OutcomeInputError(input_id, value, "value is not one of the input's values")


def _rules_of(
    version: TemplateVersion,
    example: PreviewExample,
    today: date,
    context: Mapping[str, str],
    dimensions: Sequence[InputSpec],
) -> dict[str, tuple[RuleRef, ...]]:
    """Правила манифеста и зашитые правила, которые читают каждое измерение.

    Видно по трассе: умолчания и каждая смена одной вводной (правило может быть видно только при другом значении
    соседа, например слот маршрута, который появляется у команды)."""
    contexts = [dict(context)]
    for spec in dimensions:
        contexts.extend({**context, spec.id: value} for value in spec.values if value != context[spec.id])
    found: dict[str, dict[RuleRef, None]] = {spec.id: {} for spec in dimensions}
    for combo in contexts:
        trace = resolve(version, combo, example, today).trace
        for spec in dimensions:
            for rule in reading_rules(trace, spec.id):
                found[spec.id].setdefault(rule)
    return {input_id: tuple(rules)[:MAX_DIMENSION_RULES] for input_id, rules in found.items()}


def build_atlas(  # noqa: PLR0913 — версия, набор данных, день, закрепления, предел и готовый анализ
    version: TemplateVersion,
    example: PreviewExample,
    today: date,
    *,
    pins: Mapping[str, str] | None = None,
    revision: str = "",
    limit: int = ATLAS_MAX_ROWS,
    analysis: ImpactAnalysis | None = None,
    evaluator: OutcomeEvaluator | None = None,
    exhaustive_limit: int = EXHAUSTIVE_LIMIT,
    check: Callable[[], None] | None = None,
) -> Atlas:
    """Атлас версии. `check` вызывается перед каждым расчётом: пусть бросит, когда срок вышел. `evaluator` с готовыми
    снимками комбинаций (после анализа) избавляет таблицу от повторного расчёта; он должен быть по тем же версии,
    набору данных и дню."""
    specs = input_specs(version)
    pins = dict(pins or {})
    validate_pins(specs, pins)
    defaults = normalize_inputs(specs, {}, example_defaults(example))
    context = normalize_inputs(specs, pins, example_defaults(example))
    evaluator = evaluator or OutcomeEvaluator(version, specs, example, today, check=check)
    if analysis is None:
        analysis = analyze_impact(evaluator, specs, defaults, exhaustive_limit=exhaustive_limit)

    effective = [spec for spec in specs if analysis.impacts[spec.id].effective]
    ignored = tuple(
        AtlasIgnored(spec.id, reason)
        for spec in specs
        if (reason := analysis.impacts[spec.id].ignored_reason) is not None
    )
    table_dims = [(spec.id, (pins[spec.id],) if spec.id in pins else spec.values) for spec in effective]
    base = dict(context)

    def evaluate(overrides: Mapping[str, str]) -> tuple[str, Digest]:
        snapshot = evaluator.snapshot(evaluator.values_of({**base, **overrides}))
        return snapshot.fingerprint, evaluator.digest(snapshot.fingerprint)

    # Размер таблицы проверяется до расчёта строк: слишком большой атлас не должен тратить время.
    outcomes, rows = assemble_table(table_dims, evaluate, limit=limit, check=check)
    evaluator.forget()
    rules = _rules_of(version, example, today, context, effective)
    dimensions = tuple(
        AtlasDimension(
            input=spec.id,
            values=values,
            default=values[0] if spec.id in pins else defaults[spec.id],
            affects=analysis.impacts[spec.id].sections,
            rules=rules[spec.id],
        )
        for spec, (_, values) in zip(effective, table_dims, strict=True)
    )
    return Atlas(
        revision=revision,
        dimensions=dimensions,
        ignored=ignored,
        combinations_total=combinations_count(len(spec.values) for spec in specs),
        rows_total=len(rows),
        outcomes_distinct=len(outcomes),
        outcomes=outcomes,
        rows=rows,
    )
