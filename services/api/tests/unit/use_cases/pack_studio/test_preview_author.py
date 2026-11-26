"""Предпросмотр командной комбинации: чьи личные документы собираются (`author`).

Личный документ команды имеет экземпляр на каждого автора. Раньше сборка всегда брала первый экземпляр, документы
остальных авторов увидеть было нельзя. `author` (слаг или номер с единицы) выбирает автора; без него всё как раньше:
первый автор и прежний ключ кэша. Рендер и диспетчер подменены, как в `test_preview_variants.py`."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.api.routers.v1.pack_studio import preview_build_response
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.preview import (
    PreviewAuthor,
    PreviewInputError,
    auto_examples,
    document_digest,
    pick_author,
    preview_cache_key,
    resolve_combination,
    switches_for,
    synthetic_project,
    team_authors,
)

from tests.unit.use_cases.pack_studio.outcome.synthetic import load_synthetic
from tests.unit.use_cases.pack_studio.test_preview_variants import PROJECT, TODAY, Rig, _reason

TEAM = {**PROJECT, "staffing": "team2"}
IVANOV = PreviewAuthor("ivanov", "Иванов Иван Иванович")
PETROVA = PreviewAuthor("petrova", "Петрова Мария Сергеевна")


@pytest.fixture(scope="module")
def packs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, TemplateVersion]:
    """Синтетический пак с личным документом `report` и общим `shared_spec`."""
    root = tmp_path_factory.mktemp("packs")
    return root, load_synthetic(root)


@pytest.fixture
def rig(tmp_path: Path, packs: tuple[Path, TemplateVersion]) -> Rig:
    return Rig(tmp_path, *packs)


async def test__start__team_without_author__first_author_as_before(rig: Rig) -> None:
    [build] = await rig.start("report", combination=TEAM)

    assert build.author == "ivanov"
    assert build.authors == (IVANOV, PETROVA)
    assert build.file_name == "Отчёт — Иванов.pdf"
    assert rig.renderer.requests[0].author == "ivanov"
    # Ключ кэша сборки по умолчанию прежний: автор в него не входит.
    request = rig.renderer.requests[0]
    assert build.key == preview_cache_key(
        doc_digest=_digest(rig, "report"), def_id="report", project=request.project, engine="xelatex"
    )


@pytest.mark.parametrize("author", ["2", "petrova", " petrova "])
async def test__start__author_by_number_or_slug__builds_that_authors_document(rig: Rig, author: str) -> None:
    [first] = await rig.start("report", combination=TEAM)
    [second] = await rig.start("report", combination=TEAM, author=author)

    assert second.author == "petrova"
    assert second.authors == (IVANOV, PETROVA)
    assert second.file_name == "Отчёт — Петрова.pdf"
    assert rig.renderer.requests[-1].author == "petrova"
    assert second.key != first.key
    # Другой автор это другая сборка: прежняя не отменяется.
    assert second.slot != first.slot
    response = preview_build_response(second)
    assert response.author == "petrova"
    assert [(a.slug, a.name) for a in response.authors] == [(IVANOV.slug, IVANOV.name), (PETROVA.slug, PETROVA.name)]


@pytest.mark.parametrize("author", ["1", "ivanov"])
async def test__start__first_author_named__is_the_default_build(rig: Rig, author: str) -> None:
    [default] = await rig.start("report", combination=TEAM)
    [named] = await rig.start("report", combination=TEAM, author=author)

    assert (named.key, named.author, named.slot) == (default.key, "ivanov", default.slot)
    assert named.id == default.id
    assert len(rig.renderer.requests) == 1


async def test__start__shared_document__does_not_depend_on_the_author(rig: Rig) -> None:
    [default] = await rig.start("shared_spec", combination=TEAM)
    [named, report] = await rig.start("shared_spec", "report", combination=TEAM, author="2")

    assert (named.author, named.key) == (None, default.key)
    assert named.file_name == default.file_name
    assert named.authors == (IVANOV, PETROVA)
    assert report.author == "petrova"


async def test__start__solo__author_one_is_the_only_author(rig: Rig) -> None:
    [default] = await rig.start("report", combination=PROJECT)
    [named] = await rig.start("report", combination=PROJECT, author="1")
    second = await rig.invalid("report", combination=PROJECT, author="2")
    slug = await rig.invalid("report", combination=PROJECT, author="petrova")

    assert (default.author, default.authors) == (None, ())
    assert (named.key, named.author) == (default.key, None)
    assert second.code.value == "preview_invalid"
    assert _reason(second) == ("author", "2", "the combination has authors 1..1")
    assert _reason(slug) == (
        "author",
        "petrova",
        "unknown author; authors of this combination: none, a solo work has author 1 only",
    )


@pytest.mark.parametrize(
    ("author", "reason"),
    [
        ("3", "the combination has authors 1..2"),
        ("0", "the combination has authors 1..2"),
        ("sidorov", "unknown author; authors of this combination: ivanov, petrova"),
    ],
)
async def test__start__author_outside_the_team__preview_invalid_names_the_authors(
    rig: Rig, author: str, reason: str
) -> None:
    error = await rig.invalid("report", combination=TEAM, author=author)

    assert error.code.value == "preview_invalid"
    assert _reason(error) == ("author", author, reason)
    assert rig.renderer.requests == []


def test__pick_author__english_team__slugs_come_from_the_data_set(packs: tuple[Path, TemplateVersion]) -> None:
    _, version = packs
    combo = resolve_combination(switches_for(version), {**TEAM, "lang": "en", "staffing": "team3"})
    project = synthetic_project(version, auto_examples(version)[0], combo, TODAY)

    authors = team_authors(project)

    assert [a.name for a in authors] == ["Ivan Ivanov", "Maria Petrova", "Alexey Sidorov"]
    assert pick_author(project, "3").slug == authors[2].slug
    assert pick_author(project, authors[1].slug).name == "Maria Petrova"
    with pytest.raises(PreviewInputError):
        pick_author(project, "4")


def _digest(rig: Rig, def_id: str) -> str:
    return document_digest(rig.renderer.files, rig.renderer.version, def_id, ())
