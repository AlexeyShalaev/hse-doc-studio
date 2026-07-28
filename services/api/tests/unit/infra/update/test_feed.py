from __future__ import annotations

from typing import Any

import pytest
from hse_doc_studio.core.update.entities import ReleaseEntry
from hse_doc_studio.infra.update.feed import GithubUpdateFeedGateway, releases_from_feed
from pytest_httpx import HTTPXMock

_URL = "https://api.github.com/repos/owner/repo/releases"


def _gateway(url: str = _URL) -> GithubUpdateFeedGateway:
    return GithubUpdateFeedGateway(feed_url=url, timeout_s=1.0, user_agent="test-agent")


# --- разбор фида (чистая функция) -------------------------------------------


def test__releases_from_feed__github_release_array__is_ordered_newest_first() -> None:
    # Порядок в ответе GitHub — по дате публикации; патч к старой ветке может
    # оказаться первым, поэтому сортируем по версии, а не по позиции.
    data: list[Any] = [
        {"tag_name": "v0.9.1", "draft": False, "prerelease": False},
        {"tag_name": "v0.10.0", "draft": False, "prerelease": False},
    ]

    releases = releases_from_feed(data)

    assert [r.version for r in releases] == ["0.10.0", "0.9.1"]


def test__releases_from_feed__keeps_every_release__not_just_the_newest() -> None:
    # Переключиться можно на любую версию, поэтому список нужен целиком.
    data: list[Any] = [{"tag_name": f"v0.{minor}.0"} for minor in range(5)]

    releases = releases_from_feed(data)

    assert len(releases) == 5


def test__releases_from_feed__drafts_and_prereleases__are_ignored() -> None:
    data: list[Any] = [
        {"tag_name": "v2.0.0", "draft": True, "prerelease": False},
        {"tag_name": "v1.9.0", "draft": False, "prerelease": True},
        {"tag_name": "v1.0.0", "draft": False, "prerelease": False},
    ]

    assert [r.version for r in releases_from_feed(data)] == ["1.0.0"]


def test__releases_from_feed__duplicate_versions__are_collapsed() -> None:
    data: list[Any] = [
        {"tag_name": "v1.0.0", "body": "- Первая запись"},
        {"tag_name": "v1.0.0", "body": "- Дубль"},
    ]

    releases = releases_from_feed(data)

    assert [(r.version, r.notes) for r in releases] == [("1.0.0", ("Первая запись",))]


def test__releases_from_feed__github_release__carries_date_and_note_bullets() -> None:
    # Тело релиза публикует release-please.yml из курируемых заметок; для
    # установленной сборки это единственный способ узнать, что нового в ЕЩЁ НЕ
    # поставленной версии.
    data: list[Any] = [
        {
            "tag_name": "v0.2.0",
            "published_at": "2026-08-01T10:20:30Z",
            "body": "## What's changed\n\n- Первая заметка\n* Вторая заметка\n\nПроза, не пункт.",
        }
    ]

    (release,) = releases_from_feed(data)

    assert release == ReleaseEntry(version="0.2.0", date="2026-08-01", notes=("Первая заметка", "Вторая заметка"))


def test__releases_from_feed__release_please_body__strips_markdown_and_commit_links() -> None:
    data: list[Any] = [
        {
            "tag_name": "v0.2.0",
            "body": "* **checks:** новая проверка полей ([abc1234](https://github.com/o/r/commit/abc1234))",
        }
    ]

    (release,) = releases_from_feed(data)

    assert release.notes == ("checks: новая проверка полей",)


def test__releases_from_feed__unparsable_publish_date__degrades_to_empty() -> None:
    (release,) = releases_from_feed([{"tag_name": "v0.2.0", "published_at": "не дата"}])

    assert release.date == ""


def test__releases_from_feed__single_github_release_object__is_understood() -> None:
    (release,) = releases_from_feed({"tag_name": "v0.3.0"})

    assert release.version == "0.3.0"


def test__releases_from_feed__simple_json_with_latest__uses_it() -> None:
    (release,) = releases_from_feed({"latest": "1.2.3"})

    assert release.version == "1.2.3"


def test__releases_from_feed__simple_json_with_latest_and_entries__keeps_both() -> None:
    data = {
        "latest": "1.2.0",
        "releases": [
            {"v": "1.2.0", "date": "2026-08-01", "notes": ["Заметка"]},
            {"v": "1.0.0", "notes": ["Старое"]},
        ],
    }

    releases = releases_from_feed(data)

    assert [r.version for r in releases] == ["1.2.0", "1.0.0"]
    assert releases[0].notes == ("Заметка",)


def test__releases_from_feed__simple_json_with_releases__is_ordered_newest_first() -> None:
    releases = releases_from_feed({"releases": [{"v": "1.0.0"}, {"v": "1.2.0"}]})

    assert [r.version for r in releases] == ["1.2.0", "1.0.0"]


def test__releases_from_feed__empty_feed__returns_nothing() -> None:
    # Свежий форк без релизов: «версий нет» — не то же самое, что «есть 0.0.0».
    assert releases_from_feed([]) == ()


# --- шлюз (сеть замокана) ----------------------------------------------------


async def test__probe__feed_answers__returns_checked_latest_with_its_notes(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=_URL,
        json=[
            {
                "tag_name": "v0.4.0",
                "draft": False,
                "prerelease": False,
                "published_at": "2026-08-01T00:00:00Z",
                "body": "- Что-то новое",
            }
        ],
    )

    probe = await _gateway().probe()

    assert probe.checked is True
    assert probe.latest == "0.4.0"
    assert probe.releases == (ReleaseEntry("0.4.0", "2026-08-01", ("Что-то новое",)),)
    assert probe.reason == ""


async def test__probe__feed_disabled__never_touches_the_network() -> None:
    # httpx_mock не запрашиваем намеренно: любой исходящий запрос здесь — уже баг.
    probe = await _gateway("off").probe()

    assert probe.checked is False
    assert probe.latest == ""
    assert probe.reason


@pytest.mark.parametrize("status_code", [403, 500])
async def test__probe__feed_returns_error_status__degrades_with_a_reason(
    httpx_mock: HTTPXMock, status_code: int
) -> None:
    # 403 — это лимит запросов GitHub, самый частый отказ на практике.
    httpx_mock.add_response(url=_URL, status_code=status_code)

    probe = await _gateway().probe()

    assert probe.checked is False
    assert probe.reason


async def test__probe__feed_returns_broken_json__degrades_with_a_reason(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=_URL, text="not json at all")

    probe = await _gateway().probe()

    assert probe.checked is False
    assert probe.reason


async def test__probe__network_is_down__degrades_with_a_reason(httpx_mock: HTTPXMock) -> None:
    import httpx

    httpx_mock.add_exception(httpx.ConnectError("no route to host"))

    probe = await _gateway().probe()

    assert probe.checked is False
    assert probe.reason


async def test__probe__non_http_feed_url__is_rejected_without_a_request() -> None:
    probe = await _gateway("file:///etc/passwd").probe()

    assert probe.checked is False
    assert probe.reason
