"""Прогон сценариев по версии: результат по вводным сценария, сравнение с ожиданием, покрытие правил.

Чистая функция над разобранной версией (файлов не читает, времени не берёт): сценарии, версию и набор данных
вызывающий уже прочитал. Вводные сценария ложатся поверх набора данных и умолчаний версии (`resolve`,
`normalize_inputs`), поэтому вводная, которой в версии нет, или значение вне списка это статус `error` сценария
с причиной, а не отказ.

Сценарий вне `versions` на этой версии не выполняется: он получает `unchecked` с пояснением (дизайн, 5.1).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.inputs import OutcomeInputError, input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.model import IncludeName, Outcome
from hse_doc_studio.core.pack_studio.outcome.scenario_check import (
    Change,
    Coverage,
    Failure,
    StatusName,
    coverage_of,
    judge,
)
from hse_doc_studio.core.pack_studio.outcome.scenarios import Scenario, version_matches
from hse_doc_studio.core.pack_studio.preview import AUTO_NORMAL, PreviewExample
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve


class ScenarioRunError(ValueError):
    """Результата по сценарию нет: набор данных неизвестен или битый, вводная не подходит к версии."""


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Один сценарий в прогоне (`PackScenarioRunResult` контракта)."""

    scenario: str
    status: StatusName
    fingerprint: str | None
    failures: tuple[Failure, ...]
    changes: tuple[Change, ...]
    message: str | None


@dataclass(frozen=True, slots=True)
class ScenarioRun:
    """Прогон целиком: результаты по сценариям, счётчики статусов и покрытие (`PackScenarioRun` без границы запроса)."""

    passed: int
    failed: int
    errors: int
    unchecked: int
    results: tuple[ScenarioResult, ...]
    coverage: Coverage


def example_of(scenario: Scenario, examples: Sequence[PreviewExample], wanted: str | None = None) -> PreviewExample:
    """Набор данных сценария: `wanted` (выбор на экране), иначе `example` сценария, иначе автонабор «Обычный»."""
    example_id = wanted or scenario.example or AUTO_NORMAL
    found = next((e for e in examples if e.id == example_id), None)
    if found is None:
        raise ScenarioRunError(f"example {example_id!r}: unknown example")
    if found.error is not None:
        raise ScenarioRunError(f"example {example_id!r}: {found.error}")
    return found


def resolve_scenario(  # noqa: PLR0913 — версия, наборы, сценарий и режимы расчёта
    version: TemplateVersion,
    examples: Sequence[PreviewExample],
    scenario: Scenario,
    today: date,
    *,
    inputs: Mapping[str, str] | None = None,
    wanted_example: str | None = None,
    trace: bool = True,
    revision: str = "",
    include: Collection[IncludeName] = (),
) -> Outcome:
    """Результат версии для сценария: умолчания, вводные сценария, `inputs` поверх. `include` как у `resolve`
    (`checks`). `ScenarioRunError`, если сценарий версии не подходит."""
    example = example_of(scenario, examples, wanted_example)
    try:
        return resolve(
            version,
            {**scenario.inputs, **(inputs or {})},
            example,
            today,
            trace=trace,
            revision=revision,
            include=include,
        )
    except OutcomeInputError as exc:
        raise ScenarioRunError(f"{exc.field}={exc.value!r}: {exc.reason}") from None


def run_scenarios(  # noqa: PLR0913 — версия, наборы, сценарии и день
    version: TemplateVersion,
    examples: Sequence[PreviewExample],
    scenarios: Mapping[str, Scenario | str],
    today: date,
    *,
    revision: str = "",
) -> ScenarioRun:
    """Прогон сценариев на версии. Значение `str` у сценария это ошибка файла (он не разобран): статус `error`."""
    results: list[ScenarioResult] = []
    outcomes: dict[str, Outcome] = {}
    for scenario_id, scenario in scenarios.items():
        if isinstance(scenario, str):
            results.append(ScenarioResult(scenario_id, "error", None, (), (), scenario))
            continue
        if not version_matches(scenario.versions, version.version):
            note = f"version {version.version} is outside versions: {', '.join(scenario.versions)}"
            results.append(ScenarioResult(scenario_id, "unchecked", None, (), (), note))
            continue
        try:
            outcome = resolve_scenario(version, examples, scenario, today, revision=revision)
        except ScenarioRunError as exc:
            results.append(ScenarioResult(scenario_id, "error", None, (), (), str(exc)))
            continue
        outcomes[scenario_id] = outcome
        verdict = judge(scenario, outcome)
        results.append(
            ScenarioResult(scenario_id, verdict.status, outcome.fingerprint, verdict.failures, verdict.changes, None)
        )
    counts = {status: sum(1 for r in results if r.status == status) for status in ("passed", "failed", "error")}
    return ScenarioRun(
        passed=counts["passed"],
        failed=counts["failed"],
        errors=counts["error"],
        unchecked=len(results) - sum(counts.values()),
        results=tuple(results),
        coverage=coverage_of(coverage_universe(version, examples, today), outcomes, total=len(results)),
    )


def coverage_universe(version: TemplateVersion, examples: Sequence[PreviewExample], today: date) -> tuple[Outcome, ...]:
    """Результаты, по трассам которых определяется набор правил: умолчания версии и каждая вводная, переключённая
    по одной на каждое своё значение. Это дешёвое приближение атласа (срез O4): правило, которое видно только при
    сочетании двух вводных, в набор не попадёт, пока его не увидит хотя бы один сценарий."""
    example = next((e for e in examples if e.id == AUTO_NORMAL and e.error is None), None)
    if example is None:
        return ()
    specs = input_specs(version)
    base = normalize_inputs(specs, {}, example.data.defaults if example.data is not None else {})
    combos = [base]
    combos.extend({**base, spec.id: value} for spec in specs for value in spec.values if value != base[spec.id])
    return tuple(resolve(version, combo, example, today) for combo in combos)
