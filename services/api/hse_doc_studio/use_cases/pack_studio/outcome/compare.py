"""Сравнения результатов: две стороны, «до и после» по сценариям и атласу, матрица «сценарии на разделы» (O7).

Чистые функции над разобранными версиями (файлов не читают, времени не берут): версии, наборы данных, сценарии и день
вызывающий уже прочитал (`use_cases/pack_studio/outcome_compare.py`). Расчёт идёт тем же `resolve`, что у результата и
прогона сценариев, с проверками (`checks`): иначе раздел проверок не имел бы содержания. `check` вызывается перед каждым
расчётом: пусть бросит, когда срок вышел, и перебор остановится.

- `compare_sides`: два результата (набор вводных на версии и набор данных с каждой стороны), изменения со знаками и
  причинами из трассы, сводка по разделам.
- `scenario_impacts`: каждый сценарий на версии «до» и «после»; `unchanged`, `changed` или `error` (сценарий не читается
  на одной из сторон: вводная появилась только в новой версии, набор данных пропал, вычислитель упал на манифесте).
  Сценарий вне `versions` версии шаблонов не применим к ней и в сравнение не входит.
- `atlas_rows_changed`: сколько строк таблицы атласа «после» дают на базе другой результат; вводная или значение,
  которых на базе нет, считаются изменением.
- `matrix_rows`: строка на сценарий, клетка на раздел, при `against` ещё и отличие от базы.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.atlas import decode_key
from hse_doc_studio.core.pack_studio.outcome.compare import diff_outcomes, section_deltas
from hse_doc_studio.core.pack_studio.outcome.inputs import OutcomeInputError, input_specs
from hse_doc_studio.core.pack_studio.outcome.matrix import (
    CellPrint,
    CellStatus,
    against_base,
    cell_prints,
    expectation_statuses,
)
from hse_doc_studio.core.pack_studio.outcome.model import SECTIONS, IncludeName, Outcome, SectionDelta, SectionName
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.outcome.scenario_check import Change, StatusName, judge
from hse_doc_studio.core.pack_studio.outcome.scenarios import Scenario, version_matches
from hse_doc_studio.core.pack_studio.outcome.summary import full_fingerprint
from hse_doc_studio.core.pack_studio.preview import PreviewExample
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve
from hse_doc_studio.use_cases.pack_studio.outcome.scenario_runner import ScenarioRunError, resolve_scenario

CHECKS: frozenset[IncludeName] = frozenset({"checks"})

type ImpactStatus = Literal["unchanged", "changed", "error"]


def _noop() -> None:
    return None


@dataclass(frozen=True, slots=True)
class Side:
    """Одна сторона сравнения: версия в своём состоянии, набор данных и вводные запроса (полные: сценарий, затем
    `inputs`)."""

    version: TemplateVersion
    example: PreviewExample
    inputs: Mapping[str, str]
    revision: str = ""


@dataclass(frozen=True, slots=True)
class SideResult:
    revision: str
    fingerprint: str
    inputs: dict[str, str]


@dataclass(frozen=True, slots=True)
class Comparison:
    left: SideResult
    right: SideResult
    changes: tuple[Change, ...]

    @property
    def identical(self) -> bool:
        return not self.changes

    @property
    def summary(self) -> tuple[SectionDelta, ...]:
        return section_deltas(self.changes)


class SideInputError(OutcomeInputError):
    """Вводные одной из сторон не подходят к её версии; `side` это `left` или `right`."""

    def __init__(self, side: Literal["left", "right"], error: OutcomeInputError) -> None:
        super().__init__(error.field, error.value, error.reason)
        self.side = side


def resolve_side(side: Side, today: date, *, trace: bool = True) -> Outcome:
    """Результат стороны (с проверками). `OutcomeInputError`, если вводные не подходят к версии."""
    return resolve(side.version, side.inputs, side.example, today, include=CHECKS, trace=trace, revision=side.revision)


def compare_sides(left: Side, right: Side, today: date) -> Comparison:
    """Сравнение двух результатов; ошибка вводных стороны это `SideInputError` с названием стороны."""
    try:
        before = resolve_side(left, today)
    except OutcomeInputError as exc:
        raise SideInputError("left", exc) from None
    try:
        after = resolve_side(right, today)
    except OutcomeInputError as exc:
        raise SideInputError("right", exc) from None
    return Comparison(
        SideResult(left.revision, full_fingerprint(before), dict(before.inputs)),
        SideResult(right.revision, full_fingerprint(after), dict(after.inputs)),
        diff_outcomes(before, after),
    )


def compare_body(comparison: Comparison, left_state: str, right_state: str) -> dict[str, Any]:
    """Тело ответа `compare` без полей границы запроса (пространство, пак, шаблон, версия)."""
    return {
        "left": {"state": left_state, **to_json(comparison.left)},
        "right": {"state": right_state, **to_json(comparison.right)},
        "identical": comparison.identical,
        "summary": to_json(comparison.summary),
        "changes": to_json(comparison.changes),
    }


# ── «до и после» по сценариям ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class VersionSide:
    """Версия шаблона в одном состоянии и её наборы данных (сценарии выбирают набор по id)."""

    version: TemplateVersion
    examples: tuple[PreviewExample, ...]


@dataclass(frozen=True, slots=True)
class ScenarioImpact:
    scenario: str
    name: dict[str, str]
    status: ImpactStatus
    changes: tuple[Change, ...]
    message: str | None


def _failed(scenario_id: str, name: dict[str, str], message: str) -> ScenarioImpact:
    return ScenarioImpact(scenario_id, name, "error", (), message)


def _outcome_of(
    side: VersionSide, label: str, scenario: Scenario, today: date, check: Callable[[], None]
) -> Outcome | str:
    """Результат сценария на стороне либо причина, по которой его нет (`label: причина`)."""
    check()
    try:
        return resolve_scenario(side.version, side.examples, scenario, today, include=CHECKS)
    except ScenarioRunError as exc:
        return f"{label}: {exc}"
    except Exception as exc:  # noqa: BLE001 — манифест автора, который лоадер принял, а вычислитель нет: ошибка сценария
        return f"{label}: {type(exc).__name__}: {str(exc)[:200]}"


def scenario_impacts(  # noqa: PLR0913 — стороны, их названия, сценарии, день и проверка срока
    before: VersionSide,
    after: VersionSide,
    scenarios: Mapping[str, Scenario | str],
    today: date,
    *,
    labels: tuple[str, str] = ("base", "work_tree"),
    check: Callable[[], None] = _noop,
) -> tuple[ScenarioImpact, ...]:
    """Каждый сценарий на версиях «до» и «после». Значение `str` у сценария это ошибка файла: статус `error`."""
    impacts: list[ScenarioImpact] = []
    for scenario_id, scenario in scenarios.items():
        if isinstance(scenario, str):
            impacts.append(_failed(scenario_id, {"ru": scenario_id, "en": scenario_id}, scenario))
            continue
        if not version_matches(scenario.versions, after.version.version):
            continue
        name = dict(scenario.name)
        old = _outcome_of(before, labels[0], scenario, today, check)
        new = _outcome_of(after, labels[1], scenario, today, check)
        broken = [r for r in (old, new) if isinstance(r, str)]
        if broken:
            impacts.append(_failed(scenario_id, name, "; ".join(broken)))
            continue
        assert isinstance(old, Outcome)  # noqa: S101 — сужение после проверки выше
        assert isinstance(new, Outcome)  # noqa: S101
        changes = diff_outcomes(old, new)
        impacts.append(ScenarioImpact(scenario_id, name, "changed" if changes else "unchanged", changes, None))
    return tuple(impacts)


def impact_sections(impacts: Iterable[ScenarioImpact]) -> tuple[SectionDelta, ...]:
    """Сводка изменений всех сценариев по разделам."""
    return section_deltas(change for impact in impacts for change in impact.changes)


def impact_body(impacts: Sequence[ScenarioImpact], atlas: Mapping[str, int] | None) -> dict[str, Any]:
    """Тело ответа `impact`: сводка, сценарии и находки; поля границы (ревизии, база) добавляет вызывающий.
    `new_findings` заполняет линтер результата (срез O8): здесь пусто."""
    statuses = [i.status for i in impacts]
    return {
        "summary": {
            "scenarios_total": len(impacts),
            "scenarios_changed": statuses.count("changed"),
            "scenarios_unchanged": statuses.count("unchanged"),
            "scenarios_error": statuses.count("error"),
            "sections": to_json(impact_sections(impacts)),
            "atlas": dict(atlas) if atlas is not None else None,
        },
        "scenarios": [
            {
                "scenario": i.scenario,
                "name": i.name,
                "status": i.status,
                "changes": to_json(i.changes),
                "message": i.message,
            }
            for i in impacts
        ],
        "new_findings": [],
    }


# ── атлас «до и после» ───────────────────────────────────────────────────────


def atlas_rows_changed(  # noqa: PLR0913 — строки «после», сторона «до», набор данных, день и проверка срока
    dimensions: Sequence[str],
    rows: Iterable[tuple[Sequence[str], str]],
    before: TemplateVersion,
    example: PreviewExample,
    today: date,
    *,
    check: Callable[[], None] = _noop,
) -> int:
    """Сколько строк таблицы «после» на версии «до» дают другой результат. `rows` это значения измерений по порядку
    `dimensions` и отпечаток результата «после»; остальные вводные на умолчаниях набора. Вводная, которой «до» нет,
    и значение вне её списка это изменение (на базе такой комбинации не существовало)."""
    known = {spec.id: set(spec.values) for spec in input_specs(before)}
    changed = 0
    for values, fingerprint in rows:
        overrides = dict(zip(dimensions, values, strict=True))
        if any(name not in known or value not in known[name] for name, value in overrides.items()):
            changed += 1
            continue
        check()
        if resolve(before, overrides, example, today, trace=False).fingerprint != fingerprint:
            changed += 1
    return changed


def atlas_impact(  # noqa: PLR0913 — атласы «после» и «до», версия «до», набор данных, день и проверка срока
    now: Mapping[str, Any],
    was: Mapping[str, Any],
    before: TemplateVersion,
    example: PreviewExample,
    today: date,
    *,
    check: Callable[[], None] = _noop,
) -> dict[str, int]:
    """Сводка `ImpactAtlas` по двум атласам (тела ответов `PackOutcomeAtlas`: «после» это рабочее дерево, «до» база) и
    версии «до»: строк в таблице «после», у скольких результат на базе другой, исходов до и после."""
    dimensions = [d["input"] for d in now["dimensions"]]
    fingerprints = {o["id"]: o["fingerprint"] for o in now["outcomes"]}
    rows = [(decode_key(r["key"]) if dimensions else (), fingerprints[r["outcome"]]) for r in now["rows"]]
    return {
        "rows_total": now["rows_total"],
        "rows_changed": atlas_rows_changed(dimensions, rows, before, example, today, check=check),
        "outcomes_before": was["outcomes_distinct"],
        "outcomes_after": now["outcomes_distinct"],
    }


# ── матрица ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MatrixCellResult:
    section: SectionName
    fingerprint: str
    count: int
    status: CellStatus
    changed: bool | None


@dataclass(frozen=True, slots=True)
class MatrixRowResult:
    scenario: str
    name: dict[str, str]
    inputs: dict[str, str]
    status: StatusName
    message: str | None
    cells: tuple[MatrixCellResult, ...]


def _error_row(scenario_id: str, name: dict[str, str], message: str) -> MatrixRowResult:
    cells = tuple(MatrixCellResult(section, "", 0, "error", None) for section in SECTIONS)
    return MatrixRowResult(scenario_id, name, {}, "error", message, cells)


def matrix_rows(  # noqa: PLR0913 — версия, база, сценарии, день и проверка срока
    current: VersionSide,
    scenarios: Mapping[str, Scenario | str],
    today: date,
    *,
    base: VersionSide | None = None,
    check: Callable[[], None] = _noop,
) -> tuple[MatrixRowResult, ...]:
    """Строка на сценарий версии. Со `base` у клетки `changed`: отличается ли раздел от базы (None, если сценарий на
    базе не считается). Сценарий вне `versions` версии в матрицу не входит."""
    rows: list[MatrixRowResult] = []
    for scenario_id, scenario in scenarios.items():
        if isinstance(scenario, str):
            rows.append(_error_row(scenario_id, {"ru": scenario_id, "en": scenario_id}, scenario))
            continue
        if not version_matches(scenario.versions, current.version.version):
            continue
        name = dict(scenario.name)
        outcome = _scenario_outcome(current, scenario, today, check)
        if isinstance(outcome, str):
            rows.append(_error_row(scenario_id, name, outcome))
            continue
        prints = cell_prints(outcome)
        by_section = {p.section: p for p in prints}
        differs: dict[SectionName, bool] | None = None
        if base is not None:
            old = _scenario_outcome(base, scenario, today, check)
            if not isinstance(old, str):
                differs = against_base(by_section, {p.section: p for p in cell_prints(old)})
        rows.append(_row_of(scenario_id, name, scenario, outcome, prints, differs, base is not None))
    return tuple(rows)


def _scenario_outcome(side: VersionSide, scenario: Scenario, today: date, check: Callable[[], None]) -> Outcome | str:
    check()
    try:
        return resolve_scenario(side.version, side.examples, scenario, today, trace=False, include=CHECKS)
    except ScenarioRunError as exc:
        return str(exc)
    except Exception as exc:  # noqa: BLE001 — манифест автора, который лоадер принял, а вычислитель нет
        return f"{type(exc).__name__}: {str(exc)[:200]}"


def _row_of(  # noqa: PLR0913 — сценарий, результат, клетки и сравнение с базой
    scenario_id: str,
    name: dict[str, str],
    scenario: Scenario,
    outcome: Outcome,
    prints: Sequence[CellPrint],
    differs: Mapping[SectionName, bool] | None,
    compared: bool,
) -> MatrixRowResult:
    expectation = expectation_statuses(scenario, outcome)
    cells = []
    for cell in prints:
        changed = differs[cell.section] if differs is not None else None
        # С базой изменение раздела тоже `changed`: матрица подсвечивает правку, даже если ожидания у сценария нет.
        status: CellStatus = "changed" if changed and compared else expectation[cell.section]
        cells.append(MatrixCellResult(cell.section, cell.fingerprint, cell.count, status, changed))
    return MatrixRowResult(scenario_id, name, dict(outcome.inputs), judge(scenario, outcome).status, None, tuple(cells))


def matrix_body(rows: Sequence[MatrixRowResult]) -> dict[str, Any]:
    """Тело ответа `matrix` без полей границы запроса: колонки и строки."""
    return {"columns": list(SECTIONS), "rows": to_json(rows)}


__all__ = [
    "CHECKS",
    "Comparison",
    "ImpactStatus",
    "MatrixCellResult",
    "MatrixRowResult",
    "ScenarioImpact",
    "Side",
    "SideInputError",
    "SideResult",
    "VersionSide",
    "atlas_impact",
    "atlas_rows_changed",
    "compare_body",
    "compare_sides",
    "impact_body",
    "impact_sections",
    "matrix_body",
    "matrix_rows",
    "resolve_side",
    "scenario_impacts",
]
