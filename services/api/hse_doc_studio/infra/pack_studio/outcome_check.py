"""Проверки результата для `hse-doc-studio pack check` и CI-джоба `packs` (docs/design/template-studio-outcome.md, O8).

Что проверяется для каждого шаблона:

* **Файлы сценариев** `<шаблон>/scenarios/<id>.yaml`: имя файла это id, схема `contracts/pack/scenario.schema.json`,
  разбор тем же парсером, что у Студии. Нарушение формата это **ошибка**: файл Студия не прочитает.
* **Линтер результата** (`core/pack_studio/outcome/lint*.py`): статические правила, правила по атласу и правила по
  файлам (Jinja) для живых версий: невыпущенных и старшей версии шаблона. Ошибки линтера в выпущенной версии
  (она неизменна) это предупреждения с пометкой, информационные находки не печатаются.
* **Прогон сценариев** на старшей версии, подходящей под их `versions`: вводные не подходят к версии, расхождение с
  утверждением или снимком это **предупреждение** (решение владельца: упавший сценарий предупреждает, а не блокирует,
  пока его не обновят сознательно). Покрытие правил сценариями идёт в сводку.

Лоадер версии даёт `parse_version_dir`, как в `check.py` (`load`); без лоадера этих проверок нет.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import structlog.testing
import yaml

from hse_doc_studio.core.pack_studio.outcome.coverage import RuleUniverse
from hse_doc_studio.core.pack_studio.outcome.lint import LintFinding
from hse_doc_studio.core.pack_studio.outcome.scenarios import (
    SCENARIO_SUFFIX,
    SCENARIOS_DIR,
    Scenario,
    ScenarioError,
    is_scenario_id,
    parse_scenario,
    version_matches,
)
from hse_doc_studio.core.pack_studio.preview import PreviewExample, VersionDescription
from hse_doc_studio.core.signatures.dates import DISPLAY_ZONE
from hse_doc_studio.core.template_versions import parse_version_key
from hse_doc_studio.infra.pack_studio import pack_schemas
from hse_doc_studio.infra.pack_studio.layout import PACK_MANIFEST, PackTree, template_of, template_versions
from hse_doc_studio.infra.pack_studio.outcome_lint_files import jinja_findings
from hse_doc_studio.infra.pack_studio.preview_worker import StageLimits, VersionDirs, read_examples
from hse_doc_studio.infra.template.releases import ReleaseEntry
from hse_doc_studio.infra.template.yaml_template_repository import (
    parse_pack_manifest,
    parse_version_dir,
)
from hse_doc_studio.use_cases.pack_studio.outcome.lint import lint_outcome
from hse_doc_studio.use_cases.pack_studio.outcome.scenario_runner import ScenarioRun, run_scenarios
from hse_doc_studio.use_cases.pack_studio.preview import default_example_of, examples_of

type Severity = Literal["error", "warning"]
type CheckKind = Literal["outcome", "scenario"]
type Raised = tuple[Severity, CheckKind, Path, str]  # серьёзность, проверка, путь, сообщение

_STAGE = StageLimits(max_bytes=512 * 1024 * 1024, max_files=20_000)
_FROZEN_NOTE = "выпущенная версия неизменна, исправьте в новой: "
# Расхождений сценария в сообщении не больше этого.
_MAX_DETAILS = 3


@dataclass(frozen=True)
class ScenarioSummary:
    """Сводка по шаблону для отчёта: прогон сценариев и покрытие правил (`--json`, строка в тексте)."""

    template: str
    version: str
    scenarios: int
    passed: int
    failed: int
    errors: int
    unchecked: int
    rules_total: int
    rules_covered: int
    rules_half: int
    rules_uncovered: int
    percent: float
    rows_total: int
    rows_touched: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "template": self.template,
            "version": self.version,
            "scenarios": self.scenarios,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "unchecked": self.unchecked,
            "coverage": {
                "rules_total": self.rules_total,
                "rules_covered": self.rules_covered,
                "rules_half": self.rules_half,
                "rules_uncovered": self.rules_uncovered,
                "percent": self.percent,
                "rows_total": self.rows_total,
                "rows_touched": self.rows_touched,
            },
        }


@dataclass
class OutcomeCheck:
    findings: list[Raised] = field(default_factory=list)
    summaries: list[ScenarioSummary] = field(default_factory=list)

    def add(self, severity: Severity, path: Path, message: str, *, check: CheckKind = "outcome") -> None:
        self.findings.append((severity, check, path, message))


# ── Файлы сценариев ──────────────────────────────────────────────────────────


def _scenario_files(template_dir: Path) -> list[Path]:
    folder = template_dir / SCENARIOS_DIR
    return sorted(folder.glob(f"*{SCENARIO_SUFFIX}")) if folder.is_dir() else []


def _read_scenarios(template_dir: Path, out: OutcomeCheck) -> dict[str, Scenario]:
    """Разобранные сценарии шаблона по id; нарушения формата это ошибки проверки `scenario`."""
    parsed: dict[str, Scenario] = {}
    for path in _scenario_files(template_dir):
        stem = path.stem
        if not is_scenario_id(stem):
            out.add("error", path, "имя файла не id сценария (строчная латиница, цифры, дефис)", check="scenario")
            continue
        try:
            text = path.read_text(encoding="utf-8")
            raw = yaml.safe_load(text)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            out.add(
                "error", path, f"YAML не разобран: {str(exc).splitlines()[0] if str(exc) else exc}", check="scenario"
            )
            continue
        errors = pack_schemas.validate("scenario", raw)
        for error in errors:
            out.add("error", path, error, check="scenario")
        if errors:
            continue
        try:
            parsed[stem] = parse_scenario(text)
        except ScenarioError as exc:
            out.add("error", path, exc.reason, check="scenario")
    return parsed


# ── Версия ───────────────────────────────────────────────────────────────────


def _pack_id(pack_dir: Path) -> str:
    with structlog.testing.capture_logs():
        info = parse_pack_manifest(pack_dir / PACK_MANIFEST) if (pack_dir / PACK_MANIFEST).is_file() else None
    return info.id if info is not None else pack_dir.name


@dataclass(frozen=True)
class _Loaded:
    version_dir: Path
    description: VersionDescription
    texts: Mapping[str, str]
    frozen: bool


def _load(version_dir: Path, released: Mapping[str, ReleaseEntry]) -> _Loaded | None:
    """Версия лоадером Студии, её примеры и тексты манифестов; None: лоадер её не принял (причину назвал `load`)."""
    template_dir = template_of(version_dir)
    if template_dir is None:
        return None
    pack_dir = template_dir.parent.parent
    pack_id = _pack_id(pack_dir)
    with structlog.testing.capture_logs():
        version = parse_version_dir(version_dir, pack_id, template_dir.name, released.get(version_dir.name))
    if version is None:
        return None
    dirs = VersionDirs(str(pack_dir.parent), pack_dir.name, template_dir.name, version_dir.name)
    raw = read_examples(dirs, _STAGE)
    description = VersionDescription(pack_id, template_dir.name, version, raw)
    texts = {"version.yaml": (version_dir / "version.yaml").read_text(encoding="utf-8")}
    for doc in sorted((version_dir / "files").glob("*/doc.yaml")) if (version_dir / "files").is_dir() else ():
        texts[f"files/{doc.parent.name}/doc.yaml"] = doc.read_text(encoding="utf-8")
    return _Loaded(version_dir, description, texts, version_dir.name in released)


def _default_example(loaded: _Loaded) -> tuple[PreviewExample, tuple[PreviewExample, ...]]:
    examples = examples_of(loaded.description)
    wanted = default_example_of(examples)
    return next(e for e in examples if e.id == wanted), examples


def _today() -> date:
    return datetime.now(DISPLAY_ZONE).date()


# ── Линтер результата ────────────────────────────────────────────────────────


def _raised(loaded: _Loaded, item: LintFinding) -> Raised | None:
    """Находка линтера как строка отчёта: информация не печатается, ошибка выпущенной версии это предупреждение."""
    if item.severity == "info":
        return None
    severity: Severity = "warning" if item.severity == "warning" or loaded.frozen else "error"
    where = f"{item.file}{item.pointer or ''}" if item.file else ""
    line = f":{item.line}" if item.line else ""
    prefix = _FROZEN_NOTE if loaded.frozen and item.severity == "error" else ""
    text = f"[{item.rule_id}] {prefix}{item.message}" + (f" ({where}{line})" if where else "")
    return severity, "outcome", loaded.version_dir, text


def _lint_version(loaded: _Loaded, out: OutcomeCheck, *, jinja: bool = True) -> RuleUniverse | None:
    version = loaded.description.version
    example, _ = _default_example(loaded)
    today = _today()
    result = lint_outcome(version, loaded.texts, example, today)
    extra = jinja_findings(loaded.version_dir, version, today) if jinja else ()
    for item in (*result.findings, *extra):
        raised = _raised(loaded, item)
        if raised is not None:
            out.findings.append(raised)
    return result.universe


# ── Прогон сценариев ─────────────────────────────────────────────────────────


def _newest(versions: Mapping[str, Any], patterns: tuple[str, ...]) -> str | None:
    """Старшая версия шаблона на диске, подходящая под шаблоны номеров сценария."""
    matching = [name for name in versions if version_matches(patterns, name)]
    return max(matching, key=lambda name: parse_version_key(name) or (0, 0, 0), default=None)


def _failure_text(run: ScenarioRun, scenario_id: str) -> str | None:
    result = next(r for r in run.results if r.scenario == scenario_id)
    if result.status == "error":
        return f"вводные не подходят к версии: {result.message}"
    if result.status != "failed":
        return None
    details = [f"{f.kind}: ожидалось {f.expected[:60]}, получено {f.actual[:60]}" for f in result.failures]
    changes = [f"{c.symbol} {c.label}" for c in result.changes[:_MAX_DETAILS]]
    more = f" (всего изменений {len(result.changes)})" if len(result.changes) > _MAX_DETAILS else ""
    return "расхождение с ожиданием: " + "; ".join([*details[:_MAX_DETAILS], *changes]) + more


def _run_scenarios(
    template_dir: Path,
    scenarios: Mapping[str, Scenario],
    released: Mapping[str, ReleaseEntry],
    universes: Mapping[str, RuleUniverse | None],
    out: OutcomeCheck,
) -> None:
    on_disk = template_versions(template_dir)
    by_version: dict[str, dict[str, Scenario]] = {}
    for scenario_id, scenario in scenarios.items():
        name = _newest(on_disk, scenario.versions)
        path = template_dir / SCENARIOS_DIR / f"{scenario_id}{SCENARIO_SUFFIX}"
        if name is None:
            note = f"ни одна версия шаблона не подходит под versions: {', '.join(scenario.versions)}"
            out.add("warning", path, f"сценарий {scenario_id}: {note}", check="scenario")
            continue
        by_version.setdefault(name, {})[scenario_id] = scenario
    for name, group in sorted(by_version.items()):
        loaded = _load(template_dir / "versions" / name, released)
        if loaded is None:
            continue  # лоадер версию не принял: причину назвала проверка `load`
        _, examples = _default_example(loaded)
        universe = universes.get(name)
        run = run_scenarios(loaded.description.version, examples, group, _today(), universe=universe)
        for scenario_id in group:
            problem = _failure_text(run, scenario_id)
            if problem is not None:
                path = template_dir / SCENARIOS_DIR / f"{scenario_id}{SCENARIO_SUFFIX}"
                out.add("warning", path, f"сценарий {scenario_id} на {name}: {problem}", check="scenario")
        cover = run.coverage
        out.summaries.append(
            ScenarioSummary(
                f"{template_dir.parent.parent.name}/{template_dir.name}",
                name,
                len(group),
                run.passed,
                run.failed,
                run.errors,
                run.unchecked,
                cover.rules_total,
                cover.rules_covered,
                cover.rules_half,
                cover.rules_uncovered,
                cover.percent,
                cover.rows_total,
                cover.rows_touched,
            )
        )


# ── Вход ─────────────────────────────────────────────────────────────────────


def _live_versions(tree: PackTree, template_dir: Path, released: Mapping[str, ReleaseEntry]) -> list[Path]:
    """Версии шаблона под проверкой, которые ещё можно править: невыпущенные и старшая версия шаблона."""
    in_tree = [v for v in tree.versions if template_of(v) == template_dir]
    on_disk = template_versions(template_dir)
    newest = max(on_disk, key=lambda name: on_disk[name], default=None)
    return [v for v in in_tree if v.name not in released or v.name == newest]


def check_outcome(
    tree: PackTree, released_of: Callable[[Path], Mapping[str, ReleaseEntry]], *, jinja: bool = True
) -> OutcomeCheck:
    """Файлы сценариев, линтер результата и прогон сценариев для шаблонов под проверкой."""
    out = OutcomeCheck()
    templates = sorted({*tree.templates, *(t for v in tree.versions if (t := template_of(v)) is not None)})
    for template_dir in templates:
        released = released_of(template_dir)
        scenarios = _read_scenarios(template_dir, out)
        universes: dict[str, RuleUniverse | None] = {}
        for version_dir in _live_versions(tree, template_dir, released):
            loaded = _load(version_dir, released)
            if loaded is not None:
                universes[version_dir.name] = _lint_version(loaded, out, jinja=jinja)
        if scenarios:
            _run_scenarios(template_dir, scenarios, released, universes, out)
    return out


__all__ = ["OutcomeCheck", "ScenarioSummary", "check_outcome"]
