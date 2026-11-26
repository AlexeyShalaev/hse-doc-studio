"""Паритет предпросмотра с ядром результата на реальных паках (срез O9): какие документы собираются, какой вариант и как
называется файл совпадает с `resolve`, а сценарий даёт предпросмотру те же вводные, что результату."""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.inputs import VARIANT_PREFIX, input_specs, variant_inputs
from hse_doc_studio.core.pack_studio.outcome.model import DocumentOutcome, Outcome
from hse_doc_studio.core.pack_studio.outcome.scenarios import Scenario, parse_scenario, version_matches
from hse_doc_studio.core.pack_studio.preview import (
    PreviewExample,
    PreviewInputError,
    VersionDescription,
    auto_examples,
    document_variants,
    resolve_combination,
    switches_for,
    synthetic_project,
)
from hse_doc_studio.core.template_versions import parse_version_key
from hse_doc_studio.infra.pack_studio.preview_store import FsPreviewStore
from hse_doc_studio.infra.pack_studio.workspace_files import LocalPackWorkspaceFiles
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve
from hse_doc_studio.use_cases.pack_studio.outcome.scenario_runner import resolve_scenario
from hse_doc_studio.use_cases.pack_studio.preview import (
    DocumentTarget,
    PackPreviewService,
    PreviewLimits,
    StartPreviewInput,
    document_targets,
)

from tests.unit.use_cases.pack_studio.test_preview_service import (
    ACTOR,
    WS,
    FakeDispatcher,
    FakeRenderer,
    FakeWorkspaces,
)

_PACKS = Path(__file__).resolve().parents[6] / "packs"
TODAY = date(2026, 11, 16)

# Опорная версия каждого шаблона реальных паков (закреплена: перебор комбинаций не растёт с выпуском новых версий).
TEMPLATES = [
    ("hse-cs-se", "vkr", "2026.1.2"),
    ("hse-cs-se", "coursework", "2026.1.2"),
    ("hse-cs-se", "pp", "2026.1.1"),
    ("hse-cs-sse", "coursework", "2026.1.6"),
]
_IDS = ["se-vkr", "se-coursework", "se-pp", "sse-coursework"]
_SAMPLE_STEP = 7


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    return YamlTemplateRepository(_PACKS)


def _load(repo: YamlTemplateRepository, ref: tuple[str, str, str]) -> TemplateVersion:
    found = repo.get_version(*ref)
    assert found is not None
    return found


def _desc(version: TemplateVersion) -> VersionDescription:
    return VersionDescription(version.pack_id, version.template_id, version)


def _example(version: TemplateVersion) -> PreviewExample:
    return auto_examples(version)[0]


def _combos(version: TemplateVersion) -> Iterator[dict[str, str]]:
    """Комбинации переключателей предпросмотра (без ответов анкет и вариантов), каждая седьмая у больших версий."""
    switches = switches_for(version, max_meta=None)
    product = itertools.product(*(s.values for s in switches))
    for values in itertools.islice(product, 0, None, _SAMPLE_STEP):
        yield {s.id: v for s, v in zip(switches, values, strict=True)}


def _present(outcome: Outcome) -> dict[str, DocumentOutcome]:
    return {d.id: d for d in outcome.documents if d.state != "absent"}


def _targets(
    version: TemplateVersion,
    combo: dict[str, str],
    *,
    variants: dict[str, str] | None = None,
    variant: str | None = None,
    only: str | None = None,
) -> dict[str, DocumentTarget]:
    """Документы, которые предпросмотр соберёт в комбинации, по одному запросу на документ (как экран)."""
    example = _example(version)
    project = synthetic_project(
        version, example, resolve_combination(switches_for(version, max_meta=None), combo), TODAY
    )
    found: dict[str, DocumentTarget] = {}
    for doc in (d for d in version.documents if only is None or d.id == only):
        try:
            [target] = document_targets(_desc(version), [doc.id], project, variants or {}, variant)
        except PreviewInputError as exc:
            if (exc.field, exc.reason) != ("document", "not in this combination"):
                raise
            continue
        found[doc.id] = target
    return found


@pytest.mark.parametrize("ref", TEMPLATES, ids=_IDS)
def test__parity__documents_and_file_names_equal_the_core_result_on_every_sampled_combination(
    repo: YamlTemplateRepository, ref: tuple[str, str, str]
) -> None:
    version = _load(repo, ref)
    checked = 0
    for combo in _combos(version):
        outcome = resolve(version, combo, _example(version), TODAY, trace=False)
        present = _present(outcome)
        targets = _targets(version, combo)

        assert set(targets) == set(present), combo
        for doc_id, target in targets.items():
            core = present[doc_id]
            assert target.file_name == core.instances[0].file_name, (combo, doc_id)
            chosen = next((v.id for v in core.variants if v.chosen), None)
            assert target.variant == chosen, (combo, doc_id)
        checked += 1

    assert checked > 0


@pytest.mark.parametrize("ref", TEMPLATES, ids=_IDS)
def test__parity__every_variant_input_gives_the_name_and_variant_of_the_core_result(
    repo: YamlTemplateRepository, ref: tuple[str, str, str]
) -> None:
    version = _load(repo, ref)
    specs = variant_inputs(version)
    checked = 0
    for combo in _combos(version):
        for spec in specs:
            doc_id = spec.id.removeprefix(VARIANT_PREFIX)
            for value in spec.values:
                outcome = resolve(version, {**combo, spec.id: value}, _example(version), TODAY, trace=False)
                core = _present(outcome).get(doc_id)
                by_input = _targets(version, combo, variants={doc_id: value}).get(doc_id)
                by_request = _targets(version, combo, variant=value, only=doc_id).get(doc_id)

                assert (core is None) == (by_input is None) == (by_request is None), (combo, spec.id, value)
                if core is None or by_input is None or by_request is None:
                    continue
                assert by_input.variant == by_request.variant == value
                assert by_input.file_name == by_request.file_name == core.instances[0].file_name, (combo, value)
                checked += 1

    assert (checked > 0) == bool(specs)


@pytest.mark.parametrize("ref", TEMPLATES, ids=_IDS)
def test__parity__a_variant_only_for_some_languages_is_allowed_exactly_where_the_core_says_available(
    repo: YamlTemplateRepository, ref: tuple[str, str, str]
) -> None:
    version = _load(repo, ref)
    limited = [(d, v) for d in version.documents for v in d.variants if v.supported_langs]
    for combo in _combos(version):
        outcome = resolve(version, combo, _example(version), TODAY, trace=False)
        for doc, variant in limited:
            core = _present(outcome).get(doc.id)
            if core is None:
                continue
            available = next(o.available for o in core.variants if o.id == variant.id)
            try:
                _targets(version, combo, variant=variant.id, only=doc.id)
                allowed = True
            except PreviewInputError as exc:
                if (exc.field, exc.reason) != ("variant", "not available for this language"):
                    raise
                allowed = False
            assert allowed is available, (combo, doc.id, variant.id)


# ── Сценарии реальных паков ──────────────────────────────────────────────────


def _service(tmp_path: Path, version: TemplateVersion) -> tuple[PackPreviewService, FakeRenderer]:
    renderer = FakeRenderer(version, files={"files/x": "x"})
    service = PackPreviewService(
        FakeWorkspaces(_PACKS),  # type: ignore[arg-type]
        renderer,
        FsPreviewStore(tmp_path / "previews", max_cache_entries=50, max_age_s=3600),
        FakeDispatcher(),
        limits=PreviewLimits(max_concurrent=1000),
        today=lambda: TODAY,
        files=LocalPackWorkspaceFiles(),
    )
    return service, renderer


def _scenarios(ref: tuple[str, str, str]) -> dict[str, Scenario]:
    folder = _PACKS / ref[0] / "templates" / ref[1] / "scenarios"
    return {path.stem: parse_scenario(path.read_text("utf-8")) for path in sorted(folder.glob("*.yaml"))}


def _scenario_ref(ref: tuple[str, str, str], scenario: Scenario) -> tuple[str, str, str]:
    """Версия, на которой сценарий проверяется: опорная, если она в его диапазоне `versions`, иначе старшая версия
    шаблона из диапазона (сценарий другой линии версий может нести вводные, которых в опорной версии нет). Сценарий,
    которому не подходит ни одна версия, остаётся на опорной, и тест падает на проверке диапазона."""
    if version_matches(scenario.versions, ref[2]):
        return ref
    folder = _PACKS / ref[0] / "templates" / ref[1] / "versions"
    matching = [d.name for d in folder.iterdir() if d.is_dir() and version_matches(scenario.versions, d.name)]
    newest = max(matching, key=lambda v: parse_version_key(v) or (0, 0, 0), default=ref[2])
    return (ref[0], ref[1], newest)


_SCENARIO_CASES = [
    (_scenario_ref(ref, scenario), name) for ref in TEMPLATES for name, scenario in _scenarios(ref).items()
]


@pytest.mark.parametrize(("ref", "name"), _SCENARIO_CASES, ids=lambda p: p if isinstance(p, str) else "/".join(p))
async def test__parity__a_real_scenario_builds_the_documents_of_its_core_result(
    repo: YamlTemplateRepository, tmp_path: Path, ref: tuple[str, str, str], name: str
) -> None:
    version = _load(repo, ref)
    scenario = _scenarios(ref)[name]
    assert version_matches(scenario.versions, ref[2]), "сценарию не подходит ни одна версия шаблона"
    outcome = resolve_scenario(version, tuple(auto_examples(version)), scenario, TODAY, trace=False)
    present = _present(outcome)
    service, renderer = _service(tmp_path, version)

    builds: list[Any] = []
    ids = list(present)
    for chunk in (ids[i : i + 8] for i in range(0, len(ids), 8)):
        started = await service.start(
            ACTOR, WS, ref[0], ref[1], ref[2], StartPreviewInput(documents=chunk, scenario=name)
        )
        builds.extend(started)
    await service.wait_launched()

    assert [b.document for b in builds] == ids
    for build in builds:
        core = present[build.document]
        assert build.scenario == name
        assert build.scenario_inputs == dict(scenario.inputs)
        assert build.file_name == core.instances[0].file_name, build.document
        assert build.variant == next((v.id for v in core.variants if v.chosen), None), build.document
        # Комбинация сборки это вводные результата без ответов анкет и вариантов.
        for key in ("lang", "kind", "staffing"):
            assert build.combination[key] == outcome.inputs[key]
    # Документ, которого нет в результате сценария, предпросмотр собирать отказывается.
    absent = [d.id for d in outcome.documents if d.state == "absent"]
    if absent:
        with pytest.raises(Exception, match="не подходят"):
            await service.start(
                ACTOR, WS, ref[0], ref[1], ref[2], StartPreviewInput(documents=absent[:1], scenario=name)
            )
    assert {r.def_id for r in renderer.requests} == set(ids)


def test__parity__variant_inputs_of_the_version_are_the_documents_with_open_variants(
    repo: YamlTemplateRepository,
) -> None:
    version = _load(repo, TEMPLATES[0])

    ids = {spec.id for spec in input_specs(version) if spec.id.startswith(VARIANT_PREFIX)}

    assert ids == {"variant.presentation"}  # ISO-редакции только для en: вводной не делают, выбор идёт `variant`


def test__variants__pdf_flag_marks_what_the_preview_can_turn_into_a_pdf(repo: YamlTemplateRepository) -> None:
    version = _load(repo, TEMPLATES[0])
    docs = {d.id: d for d in version.documents}

    assert {v.id: v.pdf for v in document_variants(docs["presentation"])} == {
        "pptx": True,  # PowerPoint: конвертация LibreOffice, как у сборки проекта
        "reveal": False,  # RevealJS: HTML, PDF нет
        "beamer": True,
    }
    assert {v.id: (v.pdf, v.langs) for v in document_variants(docs["technical_specification"])} == {
        "espd": (True, ()),
        "srs-29148": (True, ("en",)),
    }
