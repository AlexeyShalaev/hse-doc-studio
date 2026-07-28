from __future__ import annotations

from httpx import AsyncClient
from pytest_httpx import HTTPXMock

# Fixtures below are copied verbatim from the existing unit tests that already
# prove the parser handles this exact HTML shape:
# - _LISTING mirrors tests/unit/infra/hse_persons/test_client.py
# - _FACETS and _PROFILE mirror tests/unit/infra/hse_persons/test_parser.py
_LISTING = """
<a href="/org/persons/1" class="link link_dark large b">
  <div class="g-pic a" title="Абанкина Ирина Всеволодовна"></div>Абанкина</a>
<a href="/org/persons/2" class="link link_dark large b">
  <div class="g-pic a" title="Абанкина Татьяна Всеволодовна"></div>Абанкина</a>
<a href="/org/persons/3" class="link link_dark large b">
  <div class="g-pic a" title="Иванов Иван Иванович"></div>Иванов</a>
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

_PROFILE = """
<meta property="og:title" content="Абанкина Ирина Всеволодовна">
<meta property="og:description"
  content="Абанкина Ирина Всеволодовна, Профессор, Департамент образовательных программ,
  +74957729590 вн. 22073, Национальный исследовательский университет Высшая школа экономики">
<div>Защитила диссертацию, имеет учёную степень кандидат экономических наук, работает с 2001 года.</div>
"""


async def test__get_facets__campus_query_param__parses_and_forwards_directory_sidebar(
    test_app: AsyncClient, httpx_mock: HTTPXMock
) -> None:
    # campus=spb resolves to udept=135083 (see HsePersonsConfig.campus_udept).
    httpx_mock.add_response(url="https://www.hse.ru/org/persons/?udept=135083", method="GET", text=_FACETS)

    resp = await test_app.get("/api/v1/hse/persons/facets", params={"campus": "spb"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["campuses"][0] == {"value": "", "label": "Москва"}
    assert {"value": "135083", "label": "Санкт-Петербург"} in data["campuses"]
    dept_values = {o["value"] for o in data["departments"]}
    assert {"21292502", "678863149"} <= dept_values
    assert data["categories"] == [
        {"value": "ord", "label": "Ординарные профессора"},
        {"value": "best", "label": "Лучшие преподаватели"},
    ]
    assert data["sciranks"] == [{"value": "0", "label": "Члены РАН"}]
    assert data["positions"] == [
        {"value": "0", "label": "Руководители"},
        {"value": "1", "label": "Доценты"},
    ]


async def test__search_persons__name_and_campus_query_params__filters_and_returns_matching_persons(
    test_app: AsyncClient, httpx_mock: HTTPXMock
) -> None:
    # name="Абанкина" derives ltr=%D0%90 (URL-encoded «А»); campus=moscow has no
    # udept narrowing, so the only forwarded facet is ltr (mirrors test_client.py).
    httpx_mock.add_response(url="https://www.hse.ru/org/persons/?ltr=%D0%90", method="GET", text=_LISTING)

    resp = await test_app.get("/api/v1/hse/persons/search", params={"q": "Абанкина", "campus": "moscow", "limit": 10})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # The local name filter drops "Иванов Иван Иванович" from the same page.
    assert [p["full_name"] for p in data["persons"]] == [
        "Абанкина Ирина Всеволодовна",
        "Абанкина Татьяна Всеволодовна",
    ]
    assert data["persons"][0]["id"] == "1"
    assert data["persons"][0]["profile_url"] == "https://www.hse.ru/org/persons/1"
    assert data["persons"][0]["photo_url"] == "https://www.hse.ru/org/persons/cimage/1"
    assert data["interests"] == []


async def test__get_person_detail__existing_numeric_id__returns_parsed_profile(
    test_app: AsyncClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url="https://www.hse.ru/org/persons/25477", method="GET", text=_PROFILE)

    resp = await test_app.get("/api/v1/hse/persons/25477")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "id": "25477",
        "full_name": "Абанкина Ирина Всеволодовна",
        "position": "Профессор",
        "department": "Департамент образовательных программ",
        "degree": "Кандидат экономических наук",
        "profile_url": "https://www.hse.ru/org/persons/25477",
        "photo_url": "https://www.hse.ru/org/persons/cimage/25477",
    }


async def test__get_person_detail__directory_returns_not_found__api_returns_404(
    test_app: AsyncClient, httpx_mock: HTTPXMock
) -> None:
    # A non-200 response (e.g. hse.ru's own 404) makes the gateway degrade to
    # None, which the router maps to a 404 rather than a 500.
    httpx_mock.add_response(url="https://www.hse.ru/org/persons/999999", method="GET", status_code=404)

    resp = await test_app.get("/api/v1/hse/persons/999999")

    assert resp.status_code == 404, resp.text
