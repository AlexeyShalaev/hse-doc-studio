"""«Маршрут в этой комбинации» (template-studio.md, 5.6, срез T13) на выпущенных паках репозитория.

Тот же код, что маршрут проекта (`build_point`, `route_preset`, `default_route`), на синтетическом проекте
предпросмотра: проверяем, что переключатели людей проекта включают и выключают слоты пресета точки.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.preview import (
    auto_examples,
    resolve_combination,
    switches_for,
    synthetic_project,
)
from hse_doc_studio.core.pack_studio.submission import PairSource, ProfileRoute
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.submission import profile_route, synthetic_core_project

_PACKS = Path(__file__).resolve().parents[6] / "packs"
_TODAY = date(2026, 11, 15)


def _version(pack: str, template: str, version: str) -> TemplateVersion:
    found = YamlTemplateRepository(_PACKS).get_version(pack, template, version)
    assert found is not None
    return found


def _route(version: TemplateVersion, profile_id: str, **combo: str) -> ProfileRoute:
    example = auto_examples(version)[0]
    full = resolve_combination(switches_for(version), combo)
    synthetic = synthetic_project(version, example, full, _TODAY)
    project = synthetic_core_project("pack", "template", version, synthetic)
    profile = next(p for p in version.pack_submission.profiles if p.id == profile_id)  # type: ignore[union-attr]
    return profile_route(project, version, profile)


def _personas(route: ProfileRoute) -> list[list[str]]:
    return [[p.persona for p in step] for step in route.steps]


def test__topic_approval__company_supervisor_brings_academic_supervisor() -> None:
    version = _version("hse-cs-sse", "coursework", "2026.1.6")

    route = _route(version, "topic-approval", supervisor="company", co_supervisor="no")

    assert route.preset is True
    assert route.order_source == "profile"
    assert _personas(route) == [["author"], ["supervisor"], ["academic_supervisor"]]
    added = [(p.doc_id, p.slot_id) for p in route.pairs if p.source is PairSource.preset]
    assert added == [("topic_application", "academic_supervisor")]
    preset = next(p for p in route.pairs if p.source is PairSource.preset)
    assert preset.when is not None
    assert (preset.when.person, preset.when.role) == ("supervisor", "company")
    assert [(s.doc_id, s.slot_id) for s in route.skipped] == [("topic_application", "co_supervisor")]


def test__topic_approval__university_supervisor_skips_academic_supervisor() -> None:
    version = _version("hse-cs-sse", "coursework", "2026.1.6")

    route = _route(version, "topic-approval", supervisor="university", co_supervisor="yes")

    assert _personas(route) == [["author"], ["supervisor", "co_supervisor"]]
    assert ("topic_application", "academic_supervisor") in [(s.doc_id, s.slot_id) for s in route.skipped]
    assert route.steps[0][0].role == "author"
    assert route.steps[0][0].name


def test__checkpoint_without_signatures_has_no_steps() -> None:
    version = _version("hse-cs-sse", "coursework", "2026.1.6")

    route = _route(version, "pre-defence")

    assert route.steps == ()
    assert route.pairs == ()
    assert route.items_off == ()


def test__version_without_preset_uses_default_route() -> None:
    version = _version("hse-cs-sse", "coursework", "2026.1")
    profile = version.pack_submission.profiles[0]  # type: ignore[union-attr]

    route = _route(version, profile.id)

    assert route.preset is False
    assert route.order_source == "builtin"
    assert all(p.source is PairSource.point for p in route.pairs)
