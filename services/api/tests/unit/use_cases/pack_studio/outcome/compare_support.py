"""Общее для тестов сравнений результата (срез O7): настоящие версии, правка условия слота и эталоны.

Эталоны `PackOutcomeCompare`, `PackOutcomeImpact` и `PackOutcomeMatrix` строятся здесь тем же кодом, что отвечает на
запросы (`use_cases/pack_studio/outcome/compare.py`): тест сверяет файлы с результатом, а `fixture_bodies` по запросу
переписывает их."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.inputs import input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.outcome.scenarios import Scenario, parse_scenario
from hse_doc_studio.core.pack_studio.preview import PreviewExample, auto_examples
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.atlas import build_atlas, example_defaults
from hse_doc_studio.use_cases.pack_studio.outcome.compare import (
    Side,
    VersionSide,
    atlas_impact,
    compare_body,
    compare_sides,
    impact_body,
    matrix_body,
    matrix_rows,
    scenario_impacts,
)

ROOT = Path(__file__).resolve().parents[7]
PACKS = ROOT / "packs"
FIXTURES = ROOT / "contracts" / "pack-studio" / "fixtures"
TODAY = date(2026, 11, 16)

VKR = ("hse-cs-se", "vkr", "2026.1.2")
COURSEWORK_SE = ("hse-cs-se", "coursework", "2026.1.2")
PRACTICE = ("hse-cs-se", "pp", "2026.1.1")
COURSEWORK = ("hse-cs-sse", "coursework", "2026.1.6")
REAL_VERSIONS = (VKR, COURSEWORK_SE, PRACTICE, COURSEWORK)

# Условие слота академического руководителя курсового проекта до правки и после: «только у научрука из компании»
# и «у любого научрука» (так получены эталоны с правкой).
SLOT_BEFORE = "when: { person: supervisor, role: company }"
SLOT_AFTER = "when: { person: supervisor }"

# Ревизии эталонов (дайджесты манифестов от прототипа, значения не вычисляются).
REVISION_BASE = "sha256-5ee257ee0e5e3197"
REVISION_EDITED = "sha256-d85b5ca370523fd0"
WORKSPACE = "6f1c1c8e-1b7a-4d51-9a43-0a5b2f3c4d10"


def load(repo: YamlTemplateRepository, ref: tuple[str, str, str]) -> TemplateVersion:
    found = repo.get_version(*ref)
    assert found is not None, ref
    return found


def scenarios_of(ref: tuple[str, str, str]) -> dict[str, Scenario]:
    """Стартовые сценарии пака для шаблона версии."""
    folder = PACKS / ref[0] / "templates" / ref[1] / "scenarios"
    return {path.stem: parse_scenario(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.yaml"))}


def side_of(version: TemplateVersion) -> VersionSide:
    return VersionSide(version, tuple(auto_examples(version)))


def example_of(version: TemplateVersion) -> PreviewExample:
    return auto_examples(version)[0]


def copy_template(dest: Path, ref: tuple[str, str, str]) -> Path:
    """Копия пака с одной версией шаблона в `dest`; возвращает папку паков."""
    pack, template, version = ref
    source = PACKS / pack
    target = dest / pack
    (target / "templates" / template).mkdir(parents=True)
    shutil.copy(source / "pack.yaml", target / "pack.yaml")
    tpl = source / "templates" / template
    for name in ("template.yaml", "releases.yaml"):
        if (tpl / name).is_file():
            shutil.copy(tpl / name, target / "templates" / template / name)
    for folder in ("examples", "scenarios"):
        if (tpl / folder).is_dir():
            shutil.copytree(tpl / folder, target / "templates" / template / folder)
    shutil.copytree(tpl / "versions" / version, target / "templates" / template / "versions" / version)
    return dest


def edit_manifest(
    root: Path, ref: tuple[str, str, str], before: str, after: str, *, name: str = "version.yaml"
) -> None:
    """Правка текста манифеста версии в копии (`before` должно в нём быть)."""
    pack, template, version = ref
    path = root / pack / "templates" / template / "versions" / version / name
    text = path.read_text(encoding="utf-8")
    assert before in text, (path, before)
    path.write_text(text.replace(before, after, 1), encoding="utf-8")


def edited_coursework(dest: Path) -> TemplateVersion:
    """Курсовой проект `hse-cs-sse` 2026.1.6 с изменённым условием слота академического руководителя."""
    root = copy_template(dest, COURSEWORK)
    edit_manifest(root, COURSEWORK, SLOT_BEFORE, SLOT_AFTER)
    return load(YamlTemplateRepository(root), COURSEWORK)


def fixture_bodies(real: TemplateVersion, edited: TemplateVersion) -> dict[str, dict[str, Any]]:
    """Эталоны сравнений: `compare` двух сценариев, `impact` и `matrix` (рабочее дерево против базы)."""
    scenarios = scenarios_of(COURSEWORK)
    example = example_of(real)
    left, right = scenarios["university-supervisor"], scenarios["company-supervisor"]
    compare = compare_body(
        compare_sides(
            Side(real, example, left.inputs, REVISION_BASE), Side(real, example, right.inputs, REVISION_BASE), TODAY
        ),
        "work_tree",
        "work_tree",
    )
    header = {"workspace_id": WORKSPACE, "pack": COURSEWORK[0], "template": COURSEWORK[1], "version": COURSEWORK[2]}
    impacts = scenario_impacts(side_of(real), side_of(edited), scenarios, TODAY)
    atlas_now = _atlas(edited, example_of(edited))
    atlas_was = _atlas(real, example)
    impact = {
        **header,
        "base": "base",
        "base_revision": REVISION_BASE,
        "work_tree_revision": REVISION_EDITED,
        **impact_body(impacts, atlas_impact(atlas_now, atlas_was, real, example, TODAY)),
    }
    matrix = {
        **header,
        "state": "work_tree",
        "revision": REVISION_EDITED,
        **matrix_body(matrix_rows(side_of(edited), scenarios, TODAY, base=side_of(real))),
    }
    return {
        "PackOutcomeCompare/two_scenarios": {**header, **compare},
        "PackOutcomeImpact/coursework": impact,
        "PackOutcomeMatrix/coursework": matrix,
    }


def _atlas(version: TemplateVersion, example: PreviewExample) -> dict[str, Any]:
    specs = input_specs(version)
    assert normalize_inputs(specs, {}, example_defaults(example))
    return to_json(build_atlas(version, example, TODAY))
