"""Стартовые сценарии реальных паков (`packs/*/templates/*/scenarios/*.yaml`): формат, каноническая запись и прогон.

Файлы лежат рядом с `examples/`, вне каталога версии, и работают как регрессионные тесты пака: после правки версии
видно, какие сценарии «поехали». Тест падает, если файл не читается, записан не каноническим текстом (кнопка
«Записать снимок» в Студии дала бы другие байты) или результат версии разошёлся с утверждениями и снимком; в этом
случае сценарий обновляют сознательно (правкой утверждения или новым снимком)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from hse_doc_studio.core.pack_studio.outcome.scenarios import (
    MAX_SCENARIOS,
    Scenario,
    parse_scenario,
    scenario_id_of,
    scenario_text,
    version_matches,
)
from hse_doc_studio.core.pack_studio.preview import auto_examples
from hse_doc_studio.core.template_versions import parse_version_key
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.scenario_runner import run_scenarios

_PACKS = Path(__file__).resolve().parents[7] / "packs"
TODAY = date(2026, 11, 16)
_FILES = sorted(_PACKS.glob("*/templates/*/scenarios/*.yaml"))


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    return YamlTemplateRepository(_PACKS)


def _template(path: Path) -> tuple[str, str]:
    return path.parents[3].name, path.parents[1].name


def _versions(path: Path) -> list[str]:
    folder = path.parents[1] / "versions"
    return sorted((d.name for d in folder.iterdir() if d.is_dir()), key=lambda v: parse_version_key(v) or (0, 0, 0))


def test__real_packs__every_real_template_has_starter_scenarios() -> None:
    templates = {_template(path) for path in _FILES}

    assert {
        ("hse-cs-se", "vkr"),
        ("hse-cs-se", "coursework"),
        ("hse-cs-se", "pp"),
        ("hse-cs-sse", "coursework"),
    } <= templates


@pytest.mark.parametrize("path", _FILES, ids=lambda p: f"{p.parents[3].name}/{p.parents[1].name}/{p.stem}")
def test__real_packs__scenario_file_is_canonical_and_matches_a_real_version(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    scenario = parse_scenario(text)

    assert scenario_id_of(path.name) == path.stem
    assert scenario_text(scenario) == text, "файл записан не каноническим текстом"
    assert scenario.name.keys() >= {"ru", "en"}
    assert scenario.description.keys() >= {"ru", "en"}
    assert scenario.has_expectation
    assert scenario.snapshot is not None
    assert scenario.assertions
    assert any(version_matches(scenario.versions, v) for v in _versions(path)), "ни одна версия шаблона не подходит"


@pytest.mark.parametrize("template", sorted({_template(path) for path in _FILES}), ids=lambda t: "/".join(t))
def test__real_packs__scenarios_pass_on_the_newest_version(
    repo: YamlTemplateRepository, template: tuple[str, str]
) -> None:
    pack, name = template
    folder = _PACKS / pack / "templates" / name / "scenarios"
    files = sorted(folder.glob("*.yaml"))
    scenarios: dict[str, Scenario | str] = {
        path.stem: parse_scenario(path.read_text(encoding="utf-8")) for path in files
    }
    version_id = _versions(files[0])[-1]
    version = repo.get_version(pack, name, version_id)
    assert version is not None

    run = run_scenarios(version, tuple(auto_examples(version)), scenarios, TODAY)

    problems = {
        r.scenario: (
            r.status,
            r.message,
            [(f.kind, f.expected, f.actual) for f in r.failures],
            [c.label for c in r.changes],
        )
        for r in run.results
        if r.status != "passed"
    }
    assert problems == {}, f"версия {version_id}: сценарии разошлись с результатом"
    assert len(run.results) == len(files) <= MAX_SCENARIOS
    assert run.coverage.rules_total > 0
    assert (
        run.coverage.rules_covered + run.coverage.rules_half + run.coverage.rules_uncovered == run.coverage.rules_total
    )


def test__real_packs__scenarios_change_nothing_in_released_version_directories() -> None:
    """Сценарии лежат вне каталога версии: дайджесты выпущенных версий (`releases.yaml`) считает `test_releases.py`;
    здесь только положение файлов."""
    for path in _FILES:
        assert path.parent.name == "scenarios"
        assert path.parents[1].joinpath("template.yaml").is_file()
        assert "versions" not in path.relative_to(path.parents[1]).parts
