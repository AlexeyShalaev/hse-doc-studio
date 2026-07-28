from __future__ import annotations

import pytest
from hse_doc_studio.infra.hse_persons import parser

_CARDS = """
<div class="post person"><div class="post__content post__content_person">
  <a href="/org/persons/25477" class="link link_dark large b">
    <div class="g-pic person-avatar-small2" title="Абанкина Ирина Всеволодовна"
         alt="Абанкина Ирина Всеволодовна"
         style="background-image: url(/org/persons/cimage/25477)"></div>Абанкина Ирина Всеволодовна</a>
  <p class="with-indent7"><span>Профессор:
    <a class="link" href="#">Департамент образовательных программ</a></span></p>
</div></div>
<div class="post person"><div class="post__content post__content_person">
  <a href="/org/persons/728931370" class="link link_dark large b">
    <div class="g-pic person-avatar-small2" title="Абаева Фатима &amp; Руслановна"
         style="background-image: url(/org/persons/cimage/728931370)"></div>Абаева</a>
  <p class="with-indent7"><span>Руководитель проекта: Институт</span></p>
</div></div>
"""

_PROFILE = """
<meta property="og:title" content="Абанкина Ирина Всеволодовна">
<meta property="og:description"
  content="Абанкина Ирина Всеволодовна, Профессор, Департамент образовательных программ,
  +74957729590 вн. 22073, Национальный исследовательский университет Высшая школа экономики">
<div>Защитила диссертацию, имеет учёную степень кандидат экономических наук, работает с 2001 года.</div>
"""

_FACETS = """
<div class="h5 js-side_filter">Кампусы</div>
<li hse-value="135083">Кампус: Санкт-Петербург</li>
<li hse-value="21292502">Второй отдел<ul><li hse-value="678863149">отдел сводной отчётности</li></ul></li>
<div class="h5 js-side_filter">По категориям</div>
<input type="radio" id="category1" name="cat" value="ord"><label for="category1">Ординарные профессора</label>
<input type="radio" id="category2" name="cat" value="best"><label for="category2">Лучшие преподаватели</label>
<div class="h5 js-side_filter">По учёным званиям</div>
<input type="radio" id="scirank1" name="sr" value="0"><label for="scirank1">Члены РАН</label>
<div class="h5 js-side_filter">По должностям</div>
<input type="radio" id="position1" name="p" value="0"><label for="position1">Руководители</label>
<input type="radio" id="position2" name="p" value="1"><label for="position2">Доценты</label>
"""

_INTERESTS = """
<a href="/org/persons?intst=79192">экономика образования</a>
<a href="/org/persons?intst=79203">образовательные стандарты</a>
<a href="/org/persons?intst=79192">экономика образования</a>
"""


@pytest.mark.unit
def test__parse_cards__extracts_id_name_photo_affiliation() -> None:
    cards = parser.parse_cards(_CARDS)

    assert [c.id for c in cards] == ["25477", "728931370"]
    first = cards[0]
    assert first.full_name == "Абанкина Ирина Всеволодовна"
    assert first.profile_url == "https://www.hse.ru/org/persons/25477"
    assert first.photo_url == "https://www.hse.ru/org/persons/cimage/25477"
    assert "Департамент образовательных программ" in first.affiliation
    # HTML entities in the title are unescaped.
    assert cards[1].full_name == "Абаева Фатима & Руслановна"


@pytest.mark.unit
def test__parse_cards__empty_html__returns_empty() -> None:
    assert parser.parse_cards("<html>nothing</html>") == []


@pytest.mark.unit
def test__parse_profile__splits_og_description_and_degree() -> None:
    detail = parser.parse_profile(_PROFILE, "25477")

    assert detail.full_name == "Абанкина Ирина Всеволодовна"
    assert detail.position == "Профессор"
    # The phone segment is dropped, the org tail is cut.
    assert detail.department == "Департамент образовательных программ"
    assert detail.degree == "Кандидат экономических наук"
    assert detail.id == "25477"
    assert detail.photo_url == "https://www.hse.ru/org/persons/cimage/25477"


@pytest.mark.unit
def test__parse_profile__no_degree__leaves_empty() -> None:
    html = (
        '<meta property="og:title" content="Иван Иванов">'
        '<meta property="og:description" content="Иван Иванов, Стажёр, Лаборатория">'
    )
    detail = parser.parse_profile(html, "1")
    assert detail.position == "Стажёр"
    assert detail.department == "Лаборатория"
    assert detail.degree == ""


@pytest.mark.unit
def test__parse_facets__campuses_departments_and_all_radio_options() -> None:
    facets = parser.parse_facets(_FACETS)

    # Moscow is prepended (default, no param); СПб is parsed from the sidebar.
    assert facets.campuses[0].value == ""
    assert facets.campuses[0].label == "Москва"
    assert ("135083", "Санкт-Петербург") in [(o.value, o.label) for o in facets.campuses]
    # Nested department (own leaf label) is captured; campus items are excluded.
    dept_values = {o.value for o in facets.departments}
    assert {"21292502", "678863149"} <= dept_values
    assert "135083" not in dept_values
    # Both adjacent radio options are captured (regression: the tail must not
    # swallow the next input, which previously skipped every other option).
    assert [o.label for o in facets.categories] == ["Ординарные профессора", "Лучшие преподаватели"]
    assert [o.value for o in facets.positions] == ["0", "1"]
    assert [o.label for o in facets.sciranks] == ["Члены РАН"]


@pytest.mark.unit
def test__parse_interests__dedupes_and_caps() -> None:
    interests = parser.parse_interests(_INTERESTS, limit=10)
    assert [o.value for o in interests] == ["79192", "79203"]
    assert parser.parse_interests(_INTERESTS, limit=1) == (parser.parse_interests(_INTERESTS, limit=10)[0],)
