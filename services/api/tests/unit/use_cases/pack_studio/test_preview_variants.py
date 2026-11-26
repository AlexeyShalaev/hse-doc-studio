"""Предпросмотр с вариантом документа и сценарием (срез O9): выбор варианта, сценарий как источник комбинации,
ключ кэша, ошибки, обратная совместимость. Рендер и диспетчер подменены, как в `test_preview_service.py`; паритет с
ядром результата на реальных паках в `test_preview_parity.py`."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.routers.v1.pack_studio import preview_build_response, preview_options_response
from hse_doc_studio.core.catalog import DocumentDefinition, TemplateVersion
from hse_doc_studio.core.pack_studio.errors import PackStudioError
from hse_doc_studio.core.pack_studio.preview import (
    PREVIEW_RENDER_SALT,
    PreviewInputError,
    PreviewStatus,
    auto_examples,
    check_variant,
    document_variants,
    preview_cache_key,
    resolve_combination,
    switches_for,
    synthetic_project,
)
from hse_doc_studio.infra.pack_studio.preview_store import FsPreviewStore
from hse_doc_studio.infra.pack_studio.workspace_files import LocalPackWorkspaceFiles
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, PreviewLimits, StartPreviewInput

from tests.unit.use_cases.pack_studio.outcome.synthetic import load_synthetic
from tests.unit.use_cases.pack_studio.test_preview_service import (
    ACTOR,
    WS,
    FakeDispatcher,
    FakeRenderer,
    FakeWorkspaces,
)

_FILES = {
    "files/report/report.tex": "r",
    "files/spec/spec.tex": "s",
    "files/spec/ieee.tex": "i",
    "files/presentation/pres.tex": "p",
}

_SCENARIOS = {
    "project-ieee": """\
format: 1
name: { ru: "Проект, английский" }
inputs: { kind: project, lang: en }
""",
    "slides-beamer": """\
format: 1
name: { ru: "Презентация Beamer" }
inputs: { variant.presentation: beamer, answer.ai.used_ai: "yes" }
""",
    "team-nda": """\
format: 1
name: { ru: "Команда, NDA" }
inputs: { kind: project, staffing: team3, nda: "yes" }
""",
    "bad-input": """\
format: 1
name: { ru: "Вводной нет" }
inputs: { no_such_input: x }
""",
    "bad-value": """\
format: 1
name: { ru: "Значение вне списка" }
inputs: { lang: de }
""",
    "broken": "format: 1\nname: 3\n",
}


class Rig:
    def __init__(self, tmp_path: Path, root: Path, version: TemplateVersion, max_concurrent: int = 8) -> None:
        self.renderer = FakeRenderer(version, files=dict(_FILES))
        self.dispatcher = FakeDispatcher()
        self.store = FsPreviewStore(tmp_path / "previews", max_cache_entries=20, max_age_s=3600)
        self.service = PackPreviewService(
            FakeWorkspaces(root),  # type: ignore[arg-type]
            self.renderer,
            self.store,
            self.dispatcher,
            limits=PreviewLimits(max_concurrent=max_concurrent),
            today=lambda: date(2026, 11, 15),
            files=LocalPackWorkspaceFiles(),
        )

    async def start(self, *docs: str, **kwargs: Any) -> list[Any]:
        builds = await self.service.start(ACTOR, WS, "p", "t", "1.0.0", StartPreviewInput(documents=docs, **kwargs))
        await self.service.wait_launched()
        return builds

    async def invalid(self, *docs: str, **kwargs: Any) -> PackStudioError:
        with pytest.raises(PackStudioError) as caught:
            await self.start(*docs, **kwargs)
        return caught.value


@pytest.fixture(scope="module")
def packs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, TemplateVersion]:
    root = tmp_path_factory.mktemp("packs")
    version = load_synthetic(root)
    folder = root / "p" / "templates" / "t" / "scenarios"
    folder.mkdir()
    for name, text in _SCENARIOS.items():
        (folder / f"{name}.yaml").write_text(text, encoding="utf-8")
    return root, version


@pytest.fixture
def rig(tmp_path: Path, packs: tuple[Path, TemplateVersion]) -> Rig:
    return Rig(tmp_path, *packs)


PROJECT = {"kind": "project"}
TODAY = date(2026, 11, 15)


def _reason(error: PackStudioError) -> tuple[str, str, str]:
    ctx = error.ctx
    return str(ctx["field"]), str(ctx["value"]), str(ctx["reason"])


# ── Опции ────────────────────────────────────────────────────────────────────


async def test__options__documents_carry_variants_langs_and_the_default_variant(rig: Rig) -> None:
    options = await rig.service.options(ACTOR, WS, "p", "t", "1.0.0")
    response = preview_options_response(WS, "p", "t", "1.0.0", options)
    docs = {d.id: d for d in response.documents}

    assert [(v.id, v.langs, v.pdf) for v in docs["spec"].variants] == [("espd", [], False), ("ieee", ["en"], False)]
    assert docs["spec"].default_variant == "espd"
    assert docs["spec"].langs == ["ru", "en"]
    assert docs["report"].variants == []
    assert docs["report"].default_variant is None
    assert docs["report"].langs == ["ru", "en"]  # у документа нет своих языков: языки версии
    assert docs["nda"].langs == ["ru"]
    assert docs["presentation"].default_variant == "pptx"
    # Варианты не входят в переключатели комбинации: форма точек сдачи видит её как раньше.
    assert not any(sw.id.startswith("variant.") for sw in response.switches)


# ── Вариант ──────────────────────────────────────────────────────────────────


async def test__start__variant__goes_to_the_render_the_build_and_the_name(rig: Rig) -> None:
    [build] = await rig.start("spec", combination={**PROJECT, "lang": "en"}, variant="ieee")

    assert build.variant == "ieee"
    assert build.file_name == "Spec IEEE.pdf"
    assert rig.renderer.requests[0].variant == "ieee"
    assert preview_build_response(build).variant == "ieee"


async def test__start__no_variant__first_variant_and_its_name(rig: Rig) -> None:
    [ru, en] = [(await rig.start("spec", combination={**PROJECT, "lang": lang}))[0] for lang in ("ru", "en")]

    assert (ru.variant, ru.file_name) == ("espd", "Спецификация.pdf")
    assert (en.variant, en.file_name) == ("espd", "Spec.pdf")
    assert rig.renderer.requests[0].variant == "espd"


async def test__start__document_without_variants__no_variant_and_the_plain_name(rig: Rig) -> None:
    [build] = await rig.start("report")

    assert build.variant is None
    assert build.file_name == "Отчёт.pdf"
    assert rig.renderer.requests[0].variant is None


async def test__start__cache_key_differs_by_variant_and_a_repeat_is_a_cache_hit(rig: Rig) -> None:
    combination = {**PROJECT, "lang": "en"}
    [espd] = await rig.start("spec", combination=combination, variant="espd")
    [ieee] = await rig.start("spec", combination=combination, variant="ieee")
    await rig.dispatcher.succeed(ieee.id)
    [again] = await rig.start("spec", combination=combination, variant="ieee")

    assert espd.key != ieee.key
    assert again.cached is True
    assert again.key == ieee.key
    assert again.variant == "ieee"
    assert again.file_name == "Spec IEEE.pdf"


async def test__start__the_slot_tells_variants_apart(rig: Rig) -> None:
    combination = {**PROJECT, "lang": "en"}
    [first] = await rig.start("spec", combination=combination, variant="espd")
    [other] = await rig.start("spec", combination=combination, variant="ieee")
    rig.renderer.files["files/spec/spec.tex"] = "s2"
    [rebuilt] = await rig.start("spec", combination=combination, variant="espd")

    assert rig.dispatcher.cancelled == [first.id]  # прежняя сборка того же варианта; другой вариант не тронут
    assert other.id not in rig.dispatcher.cancelled
    assert rebuilt.id != first.id


@pytest.mark.parametrize(
    ("docs", "combination", "variant", "expected"),
    [
        (("spec",), {**PROJECT, "lang": "en"}, "nope", ("variant", "nope", "unknown variant")),
        (("spec",), {**PROJECT, "lang": "ru"}, "ieee", ("variant", "ieee", "not available for this language")),
        (("report",), PROJECT, "espd", ("variant", "espd", "the document has no variants")),
        (("spec", "presentation"), PROJECT, "beamer", ("variant", "beamer", "needs exactly one document")),
    ],
    ids=["unknown", "language", "no-variants", "several-documents"],
)
async def test__start__variant_not_allowed__preview_invalid_with_a_reason(
    rig: Rig, docs: tuple[str, ...], combination: dict[str, str], variant: str, expected: tuple[str, str, str]
) -> None:
    error = await rig.invalid(*docs, combination=combination, variant=variant)

    assert error.code.value == "preview_invalid"
    assert _reason(error) == expected
    assert rig.dispatcher.submitted == {}


async def test__start__document_not_in_the_combination__preview_invalid(rig: Rig) -> None:
    error = await rig.invalid("spec", combination={"kind": "research"}, variant="espd")

    assert _reason(error) == ("document", "spec", "not in this combination")


# ── Сценарий ─────────────────────────────────────────────────────────────────


async def test__start__scenario__inputs_set_the_combination_and_are_reported(rig: Rig) -> None:
    [build] = await rig.start("spec", scenario="project-ieee")

    assert build.scenario == "project-ieee"
    assert build.scenario_inputs == {"kind": "project", "lang": "en"}
    assert build.combination["kind"] == "project"
    assert build.combination["lang"] == "en"
    assert build.example == "auto:normal"  # набор сценария без `example`: «Обычный»
    response = preview_build_response(build)
    assert response.scenario == "project-ieee"
    assert response.scenario_inputs == {"kind": "project", "lang": "en"}


async def test__start__scenario__the_request_combination_goes_over_the_scenario(rig: Rig) -> None:
    [build] = await rig.start("spec", scenario="project-ieee", combination={"lang": "ru"})

    assert build.combination["lang"] == "ru"
    assert build.scenario_inputs == {"kind": "project", "lang": "en"}  # вводные как в файле
    assert build.file_name == "Спецификация.pdf"


async def test__start__scenario__variant_input_becomes_the_variant_of_the_document(rig: Rig) -> None:
    [build] = await rig.start("presentation", scenario="slides-beamer")

    assert build.variant == "beamer"
    assert build.file_name == "Презентация.pdf"
    assert rig.renderer.requests[0].variant == "beamer"
    # Ответ анкеты на сборку не влияет и в комбинацию проекта не попадает.
    assert not any(key.startswith(("answer.", "variant.")) for key in build.combination)


async def test__start__scenario__the_explicit_variant_beats_the_scenario_input(rig: Rig) -> None:
    [build] = await rig.start("presentation", scenario="slides-beamer", variant="pptx")

    assert build.variant == "pptx"
    assert build.file_name == "Презентация.pptx"


async def test__start__scenario__its_documents_follow_the_core_result(rig: Rig) -> None:
    team = await rig.start("report", "shared_spec", scenario="team-nda")

    assert [b.document for b in team] == ["report", "shared_spec"]
    assert team[0].combination["staffing"] == "team3"
    assert team[0].combination["nda"] == "yes"
    error = await rig.invalid("summary", scenario="team-nda")  # аннотация только у исследования
    assert _reason(error) == ("document", "summary", "not in this combination")


async def test__start__scenario__the_cache_key_follows_what_the_scenario_produces(rig: Rig) -> None:
    [by_scenario] = await rig.start("spec", scenario="project-ieee")
    [by_hand] = await rig.start("spec", combination={"kind": "project", "lang": "en"}, example="auto:normal")
    [ru] = await rig.start("spec", scenario="project-ieee", combination={"lang": "ru"})

    assert by_scenario.key == by_hand.key  # тот же проект и вариант: тот же PDF
    assert ru.key != by_scenario.key


async def test__start__scenario_and_hand_made_combination_with_the_same_result__share_the_running_build(
    rig: Rig,
) -> None:
    [by_scenario] = await rig.start("spec", scenario="project-ieee")
    [by_hand] = await rig.start("spec", combination={"kind": "project", "lang": "en"}, example="auto:normal")

    assert by_hand.id == by_scenario.id
    assert by_hand.scenario == "project-ieee"
    assert len(rig.dispatcher.submitted) == 1


@pytest.mark.parametrize(
    ("scenario", "code"),
    [("missing", "scenario_not_found"), ("Bad Id", "scenario_not_found"), ("broken", "scenario_invalid")],
)
async def test__start__scenario_file_problems__the_codes_of_the_result(rig: Rig, scenario: str, code: str) -> None:
    error = await rig.invalid("report", scenario=scenario)

    assert error.code.value == code
    assert error.ctx["scenario"] == scenario


async def test__start__scenario_without_a_file_port__not_found(
    tmp_path: Path, packs: tuple[Path, TemplateVersion]
) -> None:
    root, version = packs
    service = PackPreviewService(
        FakeWorkspaces(root),  # type: ignore[arg-type]
        FakeRenderer(version, files=dict(_FILES)),
        FsPreviewStore(tmp_path / "previews", max_cache_entries=5, max_age_s=3600),
        FakeDispatcher(),
        limits=PreviewLimits(max_concurrent=2),
    )

    with pytest.raises(PackStudioError) as caught:
        await service.start(ACTOR, WS, "p", "t", "1.0.0", StartPreviewInput(documents=["report"], scenario="team-nda"))

    assert caught.value.code.value == "scenario_not_found"


async def test__start__scenario_inputs_the_version_does_not_have__preview_invalid_on_the_scenario(rig: Rig) -> None:
    unknown = await rig.invalid("report", scenario="bad-input")
    value = await rig.invalid("report", scenario="bad-value")

    assert unknown.code.value == "preview_invalid"
    assert _reason(unknown) == ("scenario", "bad-input", "no_such_input='x': unknown switch")
    assert _reason(value) == ("scenario", "bad-value", "lang='de': value not allowed")


async def test__start__scenario_and_a_bad_request_combination__the_error_names_the_combination(rig: Rig) -> None:
    error = await rig.invalid("report", scenario="team-nda", combination={"lang": "de"})

    assert _reason(error) == ("combination.lang", "de", "value not allowed")


async def test__start__quota_counts_variant_and_scenario_builds(
    tmp_path: Path, packs: tuple[Path, TemplateVersion]
) -> None:
    rig = Rig(tmp_path, *packs, max_concurrent=2)
    combination = {**PROJECT, "lang": "en"}
    await rig.start("spec", combination=combination, variant="espd")
    await rig.start("spec", combination=combination, variant="ieee")

    error = await rig.invalid("presentation", scenario="slides-beamer")

    assert error.code.value == "preview_quota"
    assert error.ctx == {"limit": 2}
    assert len(rig.dispatcher.submitted) == 2


# ── Обратная совместимость ───────────────────────────────────────────────────


async def test__start__old_request_shape__builds_as_before_with_empty_new_fields(rig: Rig) -> None:
    [build] = await rig.start("report", example="auto:long", combination={"lang": "en"})
    response = preview_build_response(build)

    assert (build.scenario, build.scenario_inputs) == (None, {})
    assert (response.scenario, response.scenario_inputs, response.variant) == (None, {}, None)
    assert build.combination["lang"] == "en"


async def test__start__many_meta_switches_stay_limited_without_a_scenario(rig: Rig) -> None:
    # `combination` по-прежнему принимает только переключатели предпросмотра; ключи вводных результата это ошибка.
    error = await rig.invalid("report", combination={"variant.presentation": "beamer"})

    assert _reason(error) == ("combination.variant.presentation", "beamer", "unknown switch")


async def test__build_json__survives_the_store_round_trip(rig: Rig) -> None:
    [build] = await rig.start("presentation", scenario="slides-beamer")
    await rig.dispatcher.succeed(build.id)
    loaded = await rig.service.get(ACTOR, WS, build.id)

    assert loaded.status is PreviewStatus.succeeded
    assert (loaded.variant, loaded.scenario, loaded.file_name) == ("beamer", "slides-beamer", "Презентация.pdf")
    assert dict(loaded.scenario_inputs) == {"variant.presentation": "beamer", "answer.ai.used_ai": "yes"}


# ── Чистые части ─────────────────────────────────────────────────────────────


def _doc(version: TemplateVersion, doc_id: str) -> DocumentDefinition:
    return next(d for d in version.documents if d.id == doc_id)


def test__document_variants__keep_the_manifest_order_languages_and_the_engine_flag(
    packs: tuple[Path, TemplateVersion],
) -> None:
    _, version = packs

    assert [(v.id, v.langs, v.pdf) for v in document_variants(_doc(version, "spec"))] == [
        ("espd", (), False),
        ("ieee", ("en",), False),
    ]
    assert document_variants(_doc(version, "report")) == ()


def test__check_variant__language_rules(packs: tuple[Path, TemplateVersion]) -> None:
    _, version = packs
    spec = _doc(version, "spec")

    check_variant(spec, "espd", "ru")
    check_variant(spec, "ieee", "en")
    for variant, lang, reason in [
        ("ieee", "ru", "not available for this language"),
        ("other", "en", "unknown variant"),
    ]:
        with pytest.raises(PreviewInputError) as caught:
            check_variant(spec, variant, lang)
        assert (caught.value.field, caught.value.value, caught.value.reason) == ("variant", variant, reason)


def test__cache_key__variant_is_part_of_the_key_and_none_keeps_the_old_key(packs: tuple[Path, TemplateVersion]) -> None:
    _, version = packs
    project = synthetic_project(
        version, auto_examples(version)[0], resolve_combination(switches_for(version), {}), TODAY
    )
    base = {"doc_digest": "d", "def_id": "spec", "project": project, "engine": "xelatex"}
    body = {
        "salt": PREVIEW_RENDER_SALT,
        "doc": "spec",
        "inputs": "d",
        "project": project.canonical(),
        "engine": "xelatex",
    }

    old = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    assert preview_cache_key(**base) == old  # документ без вариантов и запрос без `variant`: ключ прежний
    assert preview_cache_key(**base, variant="espd") != old
    assert preview_cache_key(**base, variant="espd") != preview_cache_key(**base, variant="ieee")
    assert preview_cache_key(**base, variant="espd", checks=True) != preview_cache_key(**base, variant="espd")
    # Сборка без выбора автора: ключ прежний; документ другого автора команды это другой PDF.
    assert preview_cache_key(**base, author=None) == old
    assert preview_cache_key(**base, author="petrova") != old
    assert preview_cache_key(**base, author="petrova") != preview_cache_key(**base, author="sidorov")
