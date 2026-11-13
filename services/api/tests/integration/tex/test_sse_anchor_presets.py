"""Пресеты мест `hse-cs-sse/coursework` 2026.1.5 на якорях, настоящий TeX Live (docs/design/signing-route.md, 15.17.16).

Проект из настоящего пака (рендер файлов и `common/meta.tex`, как при создании и перед сборкой), сборка XeLaTeX в
образе раннеров и места пака по якорям сборки, как их ставит черновик маршрута:

- «Заявление о выборе темы» во всех восьми комбинациях (ru и en, с консультантом и без, научрук из ВШЭ и нет):
  якоря строк есть ровно у тех слотов, которые маршрут включает по `when`, а рамки совпадают с замерами 2026.1.4
  (15.15) до 1 мм;
- «Описание проекта» ru и en: рамка научрука над строкой даты и метки даты на её линиях; длинное название опускает
  строку 6, и место с метками идёт за ней;
- титул отчёта ru и en: место и дата автора.

Нужны docker и образ TeX в HSE_TEST_TEX_IMAGE:

    HSE_TEST_TEX_IMAGE=texlive/texlive:TL2024-historic uv run pytest tests/integration/tex -m tex --no-cov
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import SignatureSlotDef, TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import EngineType, Lang, PersonRole, ProjectKind
from hse_doc_studio.core.signatures.pack_places import SourceAnchors, pack_placement
from hse_doc_studio.core.signing_route.preset import condition_met
from hse_doc_studio.core.value_objects import Author, Person, ProjectLock, SignaturePlacement
from hse_doc_studio.infra.compile.docker_compile_executor import DockerCompileExecutor, ExecutorLimits
from hse_doc_studio.infra.compile.host_path_resolver import HostPathResolver
from hse_doc_studio.infra.compile.latexmk import SENTINEL_DONE
from hse_doc_studio.infra.project_init.template_renderer import (
    TemplateRenderer,
    instantiate_base,
    regenerate_dynamic_includes,
)
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.signatures.source_anchors import build_anchors_rel, read_anchors

from tests.factories import make_document, make_project

pytestmark = [
    pytest.mark.tex,
    pytest.mark.timeout(1800),
    pytest.mark.skipif(not os.environ.get("HSE_TEST_TEX_IMAGE"), reason="нет образа TeX (HSE_TEST_TEX_IMAGE)"),
    pytest.mark.skipif(not hasattr(os, "getuid"), reason="профиль раннера берёт uid процесса (POSIX)"),
]

_CACHE_VOLUME = "hds-test-tex-cache"
PACKS = Path(__file__).resolve().parents[5] / "packs"
PACK, TEMPLATE, VERSION, RELEASED = "hse-cs-sse", "coursework", "2026.1.5", "2026.1.4"
APPLICATION, PROPOSAL, REPORT = "topic_application", "project_proposal", "report"
CONDITIONAL = ("co_supervisor", "academic_supervisor")
TOL_MM = 1.0

SUPERVISOR = "Петров Пётр Петрович"
# Должности в одну строку ячейки, как у замеров 15.15: длинная должность опускает строки ниже, и места идут за ними.
CONSULTANT = Person(name="Сидоров Сидор Сидорович", role=PersonRole.company, title="разработчик")
SHORT_TITLE = "Контур согласования действий агента"
# Название в три-четыре строки ячейки сводки: строка 6 с датой уходит ниже.
LONG_TITLE = (
    "Контур согласования действий LLM-агента над корпоративными API с проверкой политик доступа, журналом решений "
    "и восстановлением после сбоев во внешних системах учёта"
)

# Рамки заявления по замерам 2026.1.4 (15.15, «Предлагаемые рамки»): (x, верх, ширина), страница 1. Ключ: язык,
# консультант. Научрук и автор от строк по условию не зависят, академрук стоит на первой условной строке без
# консультанта и на второй с ним.
_APPLICATION_BOXES: dict[tuple[str, bool], dict[str, tuple[float, float, float]]] = {
    ("ru", False): {"supervisor": (168, 177, 28), "author": (165, 201, 30), "academic_supervisor": (168, 216, 28)},
    ("ru", True): {
        "supervisor": (168, 177, 28),
        "author": (165, 201, 30),
        "co_supervisor": (168, 216, 28),
        "academic_supervisor": (168, 234, 28),
    },
    ("en", False): {"supervisor": (168, 148, 28), "author": (165, 173, 30), "academic_supervisor": (168, 188, 28)},
    ("en", True): {
        "supervisor": (168, 148, 28),
        "author": (165, 173, 30),
        "co_supervisor": (168, 188, 28),
        "academic_supervisor": (168, 206, 28),
    },
}
# Описание проекта (15.15): линии дня и месяца строки 6 и их метки (x, верх, ширина), высота 5 мм.
_PROPOSAL_MARKS = {
    "ru": [("day", 82, 148, 7), ("month_word", 93, 148, 24)],
    "en": [("day", 80, 126, 7), ("month_number", 89, 126, 7)],
}
_PROPOSAL_LINE_Y = {"ru": 153.0, "en": 131.0}
# Титул отчёта (15.15): рамка автора (x, верх, ширина) и правый конец линии «Подпись, Дата».
_REPORT_BOX = {"ru": ((120, 223, 28), 179.1), "en": ((31, 220, 28), 80.0)}


def _executor() -> DockerCompileExecutor:
    limits = ExecutorLimits(user=f"{os.getuid()}:{os.getgid()}" if os.getuid() != 0 else None)
    return DockerCompileExecutor(
        HostPathResolver(), image=os.environ["HSE_TEST_TEX_IMAGE"], cache_volume_name=_CACHE_VOLUME, limits=limits
    )


@dataclass(frozen=True)
class _Layout:
    lang: str = "ru"
    consultant: bool = False
    external: bool = False
    title: str = SHORT_TITLE

    @property
    def key(self) -> str:
        return f"{self.lang}-{'co' if self.consultant else 'noco'}-{'ext' if self.external else 'hse'}"


class _Built:
    """Проект на 2026.1.5 в данной вёрстке: файлы пака, `common/meta.tex` и сборки документов."""

    def __init__(self, repo: YamlTemplateRepository, version: TemplateVersion, project: Project) -> None:
        self.repo = repo
        self.version = version
        self.project = project

    @classmethod
    def create(cls, repo: YamlTemplateRepository, folder: Path, layout: _Layout, version_id: str = VERSION) -> _Built:
        version = repo.get_version(PACK, TEMPLATE, version_id)
        assert version is not None
        base = make_project(folder=folder, name=layout.title, documents=[make_document(d) for d in _DOCS])
        project = replace(
            base,
            lock=ProjectLock(pack_id=PACK, template_id=TEMPLATE, version=version_id, engine=EngineType.xelatex),
            kind=ProjectKind.project,
            lang=Lang(layout.lang),
            authors=[Author(name="Иванов Иван Иванович", group="МСПИН261")],
            supervisor=Person(
                name=SUPERVISOR,
                role=PersonRole.company if layout.external else PersonRole.university,
                title="доцент",
                degree="к.т.н.",
            ),
            co_supervisor=CONSULTANT if layout.consultant else None,
            meta={"name_en": "An approval gate for LLM agents", "form_year": "2026"},
        )
        folder.mkdir(parents=True)
        instantiate_base(project, version, repo, TemplateRenderer(), "", None)
        regenerate_dynamic_includes(project, version, repo)
        return cls(repo, version, project)

    def source(self, doc_id: str) -> str:
        doc_def = next(d for d in self.version.documents if d.id == doc_id)
        assert doc_def.source_file is not None
        return doc_def.source_file

    async def build(self, doc_id: str) -> None:
        lines = await _executor().run(
            project_folder=self.project.folder,
            source_file=self.source(doc_id),
            engine="xelatex",
            max_iterations=5,
            doc_id=doc_id,
            compile_id=uuid.uuid4(),
        )
        log = [line async for line in lines]
        assert log[-1] == SENTINEL_DONE, "\n".join(log[-60:])

    def pdf(self, doc_id: str) -> bytes:
        doc_def = next(d for d in self.version.documents if d.id == doc_id)
        assert doc_def.output_file is not None
        return (self.project.folder / doc_def.output_file).read_bytes()

    def anchors(self, doc_id: str) -> SourceAnchors:
        anchors = read_anchors(self.project.folder / build_anchors_rel(self.source(doc_id), doc_id))
        assert anchors is not None, f"{doc_id}: сборка не оставила anchors.json"
        assert anchors.problems == (), anchors.problems
        assert anchors.duplicates == (), anchors.duplicates
        return SourceAnchors(anchors)

    def slot(self, slot_id: str) -> SignatureSlotDef:
        return next(s for s in self.version.signatures_config.slots if s.id == slot_id)

    def place(self, doc_id: str, slot_id: str) -> SignaturePlacement | None:
        """Место слота на документе по якорям сборки, как его ставит черновик маршрута (R25, R32)."""
        return pack_placement(self.slot(slot_id), doc_id, None, VERSION, self.anchors(doc_id))


_DOCS = (PROPOSAL, APPLICATION, REPORT)


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    repo = YamlTemplateRepository(PACKS)
    repo.load()
    return repo


def _box(place: SignaturePlacement | None) -> tuple[float, float, float]:
    assert place is not None
    assert place.page == 1
    return place.x_mm, place.y_mm, place.width_mm


def _close(actual: tuple[float, ...], expected: tuple[float, ...]) -> bool:
    return all(abs(a - e) <= TOL_MM for a, e in zip(actual, expected, strict=True))


_COMBINATIONS = [
    _Layout(lang, consultant, external)
    for lang in ("ru", "en")
    for consultant in (False, True)
    for external in (False, True)
]


@pytest.fixture(scope="module")
def applications(repo: YamlTemplateRepository, tmp_path_factory: pytest.TempPathFactory) -> dict[str, _Built]:
    """«Заявление» во всех восьми вёрстках; сборки идут параллельно, как у раннера с несколькими задачами."""

    async def build_all() -> dict[str, _Built]:
        built = {
            layout.key: _Built.create(repo, tmp_path_factory.mktemp(layout.key) / "proj", layout)
            for layout in _COMBINATIONS
        }
        await asyncio.gather(*(b.build(APPLICATION) for b in built.values()))
        return built

    return asyncio.run(build_all())


@pytest.mark.parametrize("layout", _COMBINATIONS, ids=lambda layout: layout.key)
def test__application__anchors_follow_when_and_places_match_the_measurements(
    applications: dict[str, _Built], layout: _Layout
) -> None:
    built = applications[layout.key]
    src = built.anchors(APPLICATION)
    profile = next(p for p in built.version.pack_submission.profiles if p.id == "topic-approval")

    # Строка напечатана ровно у тех слотов сверх точки, которые маршрут включает по `when` (15.17.8).
    for preset in profile.signing_slots:
        assert preset.when is not None
        expected = condition_met(preset.when, built.project)
        assert (src.line(preset.slot_id) is not None) is expected, (preset.slot_id, layout)
    # Пары точки: научрук и автор всегда.
    assert src.line("supervisor") is not None
    assert src.line("author") is not None

    boxes = _APPLICATION_BOXES[(layout.lang, layout.consultant)]
    for slot_id in ("supervisor", "author", *CONDITIONAL):
        place = built.place(APPLICATION, slot_id)
        if src.line(slot_id) is None:
            assert place is None, slot_id
            continue
        assert _close(_box(place), boxes[slot_id]), (slot_id, _box(place), boxes[slot_id])
        assert place is not None
        assert place.from_pack is not None
        assert place.from_pack.anchor == slot_id
        # Правый край рамки у конца линии «Подпись» (195 мм), верх на 10 мм выше линии (у автора на 11).
        line = src.line(slot_id)
        assert line is not None
        assert place.x_mm + place.width_mm == pytest.approx(line.x_mm + line.width_mm, abs=0.15), slot_id
        assert place.x_mm + place.width_mm == pytest.approx(195.0, abs=0.15), slot_id
        assert place.y_mm == pytest.approx(line.y_mm - (11.0 if slot_id == "author" else 10.0), abs=0.05), slot_id


@pytest.fixture(scope="module")
def proposals(repo: YamlTemplateRepository, tmp_path_factory: pytest.TempPathFactory) -> dict[str, _Built]:
    layouts = {
        "ru": _Layout("ru"),
        "en": _Layout("en", consultant=True),
        "ru-long": _Layout("ru", title=LONG_TITLE),
        "en-long": _Layout("en", title=LONG_TITLE),
    }

    async def build_all() -> dict[str, _Built]:
        built = {key: _Built.create(repo, tmp_path_factory.mktemp(key) / "proj", lay) for key, lay in layouts.items()}
        await asyncio.gather(*(b.build(PROPOSAL) for b in built.values()), *(b.build(REPORT) for b in built.values()))
        return built

    return asyncio.run(build_all())


@pytest.mark.parametrize("lang", ["ru", "en"])
def test__proposal__supervisor_place_above_the_date_line_marks_on_it(proposals: dict[str, _Built], lang: str) -> None:
    built = proposals[lang]
    place = built.place(PROPOSAL, "supervisor")

    assert place is not None
    line = built.anchors(PROPOSAL).line("supervisor")
    assert line is not None
    assert line.y_mm == pytest.approx(_PROPOSAL_LINE_Y[lang], abs=TOL_MM)
    # Рамка в пустой ячейке над строкой даты: низ рамки (высота 0,4 ширины) выше меток даты, а плашка открепленной ЭП
    # (70 мм влево от правого края рамки) не заходит в левую колонку сводки, то есть начинается не левее строки даты.
    assert (place.x_mm, place.width_mm) == (pytest.approx(line.x_mm + 30.0, abs=0.05), 40.0)
    assert place.x_mm + place.width_mm - 70.0 >= line.x_mm - 0.05
    assert place.y_mm == pytest.approx(line.y_mm - 22.0, abs=0.05)
    assert place.y_mm + 0.4 * place.width_mm < min(m.y_mm for m in place.dates)
    marks = [(m.format.value, m.x_mm, m.y_mm, m.width_mm) for m in place.dates]
    assert [m[0] for m in marks] == [m[0] for m in _PROPOSAL_MARKS[lang]]
    for actual, expected in zip(marks, _PROPOSAL_MARKS[lang], strict=True):
        assert _close(actual[1:], expected[1:]), (actual, expected)


@pytest.mark.parametrize("lang", ["ru", "en"])
def test__proposal__long_title_moves_the_date_line_and_the_place_follows(
    proposals: dict[str, _Built], lang: str
) -> None:
    short = proposals[lang].place(PROPOSAL, "supervisor")
    long = proposals[f"{lang}-long"].place(PROPOSAL, "supervisor")
    short_line = proposals[lang].anchors(PROPOSAL).line("supervisor")
    long_line = proposals[f"{lang}-long"].anchors(PROPOSAL).line("supervisor")

    assert short is not None
    assert long is not None
    assert short_line is not None
    assert long_line is not None
    shift = long_line.y_mm - short_line.y_mm
    assert shift > 5.0  # название в несколько строк ячейки
    assert long.y_mm - short.y_mm == pytest.approx(shift, abs=0.15)
    assert (long.x_mm, long.width_mm) == (short.x_mm, short.width_mm)
    for before, after in zip(short.dates, long.dates, strict=True):
        assert after.y_mm - before.y_mm == pytest.approx(shift, abs=0.15)
        assert after.x_mm == before.x_mm


@pytest.mark.parametrize("lang", ["ru", "en"])
def test__report__author_place_and_date_on_the_title(proposals: dict[str, _Built], lang: str) -> None:
    built = proposals[lang]
    place = built.place(REPORT, "author")
    expected, line_end = _REPORT_BOX[lang]

    assert _close(_box(place), expected), (_box(place), expected)
    assert place is not None
    [mark] = place.dates
    assert mark.format.value == "date_numeric"
    # Дата справа на той же линии, рамка подписи слева: не пересекаются.
    assert mark.x_mm + mark.width_mm == pytest.approx(line_end - 1.0, abs=0.2)
    assert mark.x_mm >= place.x_mm + place.width_mm
    # Супервизор на титуле отчёта не на якоре: точка `final` его не требует.
    assert built.anchors(REPORT).line("supervisor") is None


@pytest.fixture(scope="module")
def released(repo: YamlTemplateRepository, tmp_path_factory: pytest.TempPathFactory) -> _Built:
    """Те же данные проекта на выпущенной 2026.1.4 (без якорей)."""

    async def build_all() -> _Built:
        built = _Built.create(repo, tmp_path_factory.mktemp("released") / "proj", _Layout("ru"), RELEASED)
        await asyncio.gather(*(built.build(doc_id) for doc_id in _DOCS))
        return built

    return asyncio.run(build_all())


@pytest.mark.parametrize("doc_id", _DOCS)
def test__patch__same_pdf_as_the_released_version(
    released: _Built, applications: dict[str, _Built], proposals: dict[str, _Built], doc_id: str
) -> None:
    # Якоря ничего не печатают (15.17.5): обновление на 2026.1.5 не даёт «Есть изменения» у документов на подписании.
    patched = applications["ru-noco-hse"] if doc_id == APPLICATION else proposals["ru"]

    assert patched.pdf(doc_id) == released.pdf(doc_id)
