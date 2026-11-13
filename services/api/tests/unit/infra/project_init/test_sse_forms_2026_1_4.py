"""КП СПИ 2026.1.4: город и год из проекта, заявление на языке проекта, строки заявления по условию."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.infra.project_init.template_renderer import _build_info, _render_text

_FILES = Path(__file__).resolve().parents[6] / "packs/hse-cs-sse/templates/coursework/versions/2026.1.4/files"
_META = _FILES / "common/meta.tex.j2"
_APPLICATION = _FILES / "topic_application/topic_application.tex"


def _render(project: dict[str, Any], build: dict[str, Any] | None = None) -> str:
    context: dict[str, Any] = {"project": project, "author": {}}
    if build is not None:
        context["build"] = build
    return _render_text(_META.read_text(encoding="utf-8"), context, _META)


def _macro(rendered: str, name: str) -> str:
    match = re.search(r"\\newcommand\{\\" + name + r"\}\{%\n(.*)\}", rendered)
    assert match is not None, name
    return match.group(1)


def _flag(rendered: str, name: str) -> bool:
    match = re.search(r"\\" + name + r"(true|false)", rendered)
    assert match is not None, name
    return match.group(1) == "true"


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({}, "Moscow"),
        ({"city": "Москва"}, "Moscow"),
        ({"city": " Санкт-Петербург "}, "Saint Petersburg"),
        ({"city": "Нижний Новгород"}, "Nizhny Novgorod"),
        ({"city": "Пермь"}, "Perm"),
        ({"city": "Казань"}, "Казань"),
        ({"city": "Москва", "city_en": "Moscow, Russia"}, "Moscow, Russia"),
    ],
)
def test__city_en__known_cities_translated_others_as_is_field_wins(meta: dict[str, str], expected: str) -> None:
    assert _macro(_render({"meta": meta}), "hseCityEn") == expected


def test__form_year__field_then_build_year_then_tex_year() -> None:
    assert _macro(_render({"meta": {"form_year": "2025"}}, {"year": 2026}), "hseFormYear") == "2025"
    assert _macro(_render({"meta": {}}, {"year": 2026}), "hseFormYear") == "2026"
    # Старая Студия без `build`: год сборки считает TeX.
    assert _macro(_render({"meta": {}}), "hseFormYear") == r"\the\year"


def test__signdateblank_and_city_year__use_form_year() -> None:
    rendered = _render({"meta": {}}, {"year": 2026})

    assert r"\newcommand{\signdateblank}{«\rule{0.8cm}{0.4pt}» \rule{2.5cm}{0.4pt} \hseFormYear~г.}" in rendered
    assert r"\NewDocumentCommand{\hseCityYear}{s O{\hseFormYear}}" in rendered
    assert r"\the\year" not in rendered


def test__build_info__new_year_by_moscow_time() -> None:
    # 31 декабря 21:30 UTC — уже 1 января по Москве.
    assert _build_info(datetime(2026, 12, 31, 21, 30, tzinfo=UTC)) == {"year": 2027, "date": "2027-01-01"}
    assert _build_info(datetime(2026, 12, 31, 20, 59, tzinfo=UTC))["year"] == 2026


@pytest.mark.parametrize(
    ("project", "lang_en", "co", "external"),
    [
        ({"lang": "ru"}, False, False, False),
        ({"lang": "en", "co_supervisor": {"name": "С. С. Сидоров"}}, True, True, False),
        ({"lang": "ru", "supervisor": {"name": "П. П. Петров", "role": "company"}}, False, False, True),
        ({"lang": "ru", "supervisor": {"name": "П. П. Петров", "role": "university"}}, False, False, False),
        ({"lang": "ru", "co_supervisor": {"name": ""}}, False, False, False),
    ],
)
def test__flags__language_consultant_external_supervisor(
    project: dict[str, Any], lang_en: bool, co: bool, external: bool
) -> None:
    rendered = _render(project)

    assert _flag(rendered, "hseLangEn") is lang_en
    assert _flag(rendered, "hseHasCoSupervisor") is co
    assert _flag(rendered, "hseExternalSupervisor") is external


def test__academic_supervisor_en__default_latin_or_project_person() -> None:
    assert _macro(_render({}), "hseAcademicSupervisorShortNameEn") == "Shershakov S.A."
    rendered = _render({"academic_supervisor": {"name": "И. И. Иванов"}})
    assert _macro(rendered, "hseAcademicSupervisorShortNameEn") == "Иванов И.И."


def _branch(source: str, flag: str, marker: str) -> str:
    """Текст условной строки: от `\\if<flag>`, после которого стоит `marker`, до ближайшего `\\fi`."""
    for match in re.finditer(r"\\if" + flag + r"\b", source):
        end = source.index("\\fi\n", match.end())
        block = source[match.end() : end]
        if marker in block:
            return block
    raise AssertionError(f"{marker!r} не под \\if{flag}")


def test__application__one_page_per_language_and_conditional_lines() -> None:
    source = _APPLICATION.read_text(encoding="utf-8")
    body = source[source.index(r"\begin{document}") :]

    assert r"\clearpage" not in body
    english, russian = body.split("\n\\else\n% ====", 1)
    assert r"\ifhseLangEn" in english
    assert "APPLICATION FORM" in english
    assert "ЗАЯВЛЕНИЕ" in russian
    assert "APPLICATION FORM" not in russian
    # Строки «при наличии» целиком под условием, на обеих страницах.
    assert "Signature" in _branch(english, "hseHasCoSupervisor", "Consultant")
    assert "Signature" in _branch(english, "hseExternalSupervisor", "Consent of the academic supervisor")
    assert "Подпись" in _branch(russian, "hseHasCoSupervisor", "Консультант")
    assert "Подпись" in _branch(russian, "hseExternalSupervisor", "Согласие академического руководителя")
    # Город и год одной строкой из проекта, ничего не вшито.
    assert body.count(r"\hseCityYear") == 2
    assert "Moscow" not in body
    assert r"\the\year" not in body
