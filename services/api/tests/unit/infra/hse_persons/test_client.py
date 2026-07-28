from __future__ import annotations

import time

import pytest
from hse_doc_studio.core.hse_persons.entities import HsePersonQuery
from hse_doc_studio.infra.hse_persons.client import HseHttpPersonsGateway

_LISTING = """
<a href="/org/persons/1" class="link link_dark large b">
  <div class="g-pic a" title="Абанкина Ирина Всеволодовна"></div>Абанкина</a>
<a href="/org/persons/2" class="link link_dark large b">
  <div class="g-pic a" title="Абанкина Татьяна Всеволодовна"></div>Абанкина</a>
<a href="/org/persons/3" class="link link_dark large b">
  <div class="g-pic a" title="Иванов Иван Иванович"></div>Иванов</a>
"""


def _gateway(*, min_interval: float = 0.0) -> HseHttpPersonsGateway:
    return HseHttpPersonsGateway(
        base_url="https://www.hse.ru",
        list_path="/org/persons/",
        campus_udept={"moscow": "", "spb": "135083"},
        user_agent="test",
        request_timeout_s=5.0,
        min_request_interval_s=min_interval,
        max_concurrency=2,
        retries=1,
        list_cache_ttl_s=900.0,
        detail_cache_ttl_s=900.0,
        facets_cache_ttl_s=900.0,
    )


class _Recorder:
    def __init__(self, body: str | None) -> None:
        self.body = body
        self.urls: list[str] = []

    async def __call__(self, url: str) -> str | None:
        self.urls.append(url)
        return self.body


@pytest.mark.unit
async def test__search__name_and_campus_query__filters_by_name_and_derives_ltr_url() -> None:
    gw = _gateway()
    rec = _Recorder(_LISTING)
    gw._get = rec  # type: ignore[method-assign]

    result = await gw.search(HsePersonQuery(name="Абанкина", campus="moscow", limit=10))

    assert [p.full_name for p in result.persons] == [
        "Абанкина Ирина Всеволодовна",
        "Абанкина Татьяна Всеволодовна",
    ]
    # ltr derived from the first letter of the name (URL-encoded «А»).
    assert rec.urls == ["https://www.hse.ru/org/persons/?ltr=%D0%90"]


@pytest.mark.unit
async def test__search__finer_name_over_same_letter__served_from_cache_without_refetch() -> None:
    gw = _gateway()
    rec = _Recorder(_LISTING)
    gw._get = rec  # type: ignore[method-assign]
    await gw.search(HsePersonQuery(name="Абанкина", campus="moscow", limit=10))

    finer = await gw.search(HsePersonQuery(name="абанкина т", campus="moscow", limit=10))

    assert [p.full_name for p in finer.persons] == ["Абанкина Татьяна Всеволодовна"]
    assert len(rec.urls) == 1


@pytest.mark.unit
async def test__search__no_narrowing__refuses_without_fetch() -> None:
    gw = _gateway()
    rec = _Recorder(_LISTING)
    gw._get = rec  # type: ignore[method-assign]

    result = await gw.search(HsePersonQuery(campus="moscow"))

    assert result.persons == ()
    assert rec.urls == []


@pytest.mark.unit
async def test__search__facets_forwarded_as_semicolon_query() -> None:
    gw = _gateway()
    rec = _Recorder(_LISTING)
    gw._get = rec  # type: ignore[method-assign]

    await gw.search(HsePersonQuery(campus="spb", category="best", position="5"))

    assert rec.urls == ["https://www.hse.ru/org/persons/?udept=135083;category=best;position=5"]


@pytest.mark.unit
async def test__search_and_get_detail__fetch_returns_none__degrade_to_empty_result() -> None:
    gw = _gateway()
    gw._get = _Recorder(None)  # type: ignore[method-assign]

    persons = (await gw.search(HsePersonQuery(name="Иванов"))).persons
    detail = await gw.get_detail("123")

    assert persons == ()
    assert detail is None


@pytest.mark.unit
async def test__get_detail__non_numeric_id__returns_none() -> None:
    gw = _gateway()
    gw._get = _Recorder(None)  # type: ignore[method-assign]

    # A non-numeric id never touches the network.
    assert await gw.get_detail("abc") is None


@pytest.mark.unit
async def test__throttle__enforces_min_interval_between_requests() -> None:
    gw = _gateway(min_interval=0.15)
    gw._get = _Recorder(_LISTING)  # type: ignore[method-assign]  # bypassed: we call _throttle directly

    start = time.monotonic()
    await gw._throttle()
    await gw._throttle()
    await gw._throttle()
    elapsed = time.monotonic() - start

    # Two gaps of ≥0.15s between three requests.
    assert elapsed >= 0.30 - 0.02
