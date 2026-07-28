from __future__ import annotations

import json

from hse_doc_studio.api.config import settings
from httpx import AsyncClient

from tests.integration.api.system.conftest import FakeUpdateFeed

# Курируемые заметки — данные, а не код: сверяемся с тем же release-notes.json,
# который приложение читает при старте.
_CURATED = json.loads(settings.release_notes_file.read_text(encoding="utf-8"))["releases"]

# --- check-updates ------------------------------------------------------------


async def test__api__check_updates__feed_has_newer_version__reports_it_available(
    app_with_newer_release: AsyncClient,
) -> None:
    resp = await app_with_newer_release.post("/api/v1/system/check-updates")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current"] == settings.get_app_version()
    assert body["latest"] == "999.0.0"
    assert body["available"] is True
    assert body["checked"] is True
    assert body["checked_at"]
    assert body["reason"] == ""


async def test__api__check_updates__answer_is_cached__system_info_reports_it_without_asking_again(
    app_with_newer_release: AsyncClient,
    newer_release_feed: FakeUpdateFeed,
) -> None:
    # Ради этого проверка и переехала на бэкенд: результат переживает перезагрузку
    # страницы и общий для всех вкладок, а фид не дёргается на каждый экран.
    before = (await app_with_newer_release.get("/api/v1/system/info")).json()
    assert before["update_available"] is False
    assert before["update_checked_at"] is None

    await app_with_newer_release.post("/api/v1/system/check-updates")

    after = (await app_with_newer_release.get("/api/v1/system/info")).json()
    assert after["update_available"] is True
    assert after["latest_version"] == "999.0.0"
    assert after["update_checked_at"]
    # Заметки о ещё не установленной версии на машине больше взять неоткуда, поэтому
    # они кэшируются вместе с номером — иначе «Что нового» пустело бы в новой вкладке.
    assert after["latest_release_date"] == "2026-08-01"
    assert after["latest_release_notes"] == ["Что-то новое"]
    assert newer_release_feed.calls == 1, "/system/info не должен ходить в фид"


async def test__api__check_updates__feed_unreachable__falls_back_to_the_cached_answer(
    app_with_newer_release: AsyncClient,
    app_with_unreachable_feed: AsyncClient,
) -> None:
    # Оба приложения смотрят в один data_dir (общий tmp_path), поэтому второе
    # видит кэш, записанный первым — как перезапуск с пропавшей сетью.
    await app_with_newer_release.post("/api/v1/system/check-updates")

    resp = await app_with_unreachable_feed.post("/api/v1/system/check-updates")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["checked"] is False
    assert body["reason"] == "feed is unreachable"
    # Знание «вышла 999.0.0» пережило потерю сети — иначе кнопка обновления
    # осталась бы без цели ровно в тот момент, когда она нужнее всего.
    assert body["latest"] == "999.0.0"
    assert body["available"] is True
    assert body["checked_at"], "время прошлой удачной проверки должно сохраниться"


async def test__api__check_updates__feed_unreachable_and_no_cache__degrades_with_a_reason(
    app_with_unreachable_feed: AsyncClient,
) -> None:
    resp = await app_with_unreachable_feed.post("/api/v1/system/check-updates")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Недоступный фид — не ошибка приложения: отвечаем «проверить не удалось»,
    # а не 500, иначе «О программе» падал бы вместе с чужим сервисом.
    assert body["checked"] is False
    assert body["reason"] == "feed is unreachable"
    assert body["latest"] == settings.get_app_version()
    assert body["available"] is False
    assert body["checked_at"] is None


# --- release notes ------------------------------------------------------------


async def test__api__release_notes__default_language__returns_curated_russian_notes(
    test_app: AsyncClient,
) -> None:
    resp = await test_app.get("/api/v1/system/release-notes")

    assert resp.status_code == 200, resp.text
    releases = resp.json()["releases"]
    assert len(releases) == len(_CURATED)
    assert releases[0]["version"] == _CURATED[0]["version"]
    assert releases[0]["notes"] == [note["ru"] for note in _CURATED[0]["notes"]]


async def test__api__release_notes__english_interface__returns_english_notes(
    test_app: AsyncClient,
) -> None:
    resp = await test_app.get(
        "/api/v1/system/release-notes",
        headers={"X-Interface-Language": "en"},
    )

    assert resp.status_code == 200, resp.text
    releases = resp.json()["releases"]
    assert releases[0]["notes"] == [note["en"] for note in _CURATED[0]["notes"]]


async def test__api__release_notes__offline_install__still_answers(
    app_with_unreachable_feed: AsyncClient,
) -> None:
    # Заметки — локальные данные сборки: «Что нового» обязано открываться и там,
    # где фид выключен или недоступен.
    resp = await app_with_unreachable_feed.get("/api/v1/system/release-notes")

    assert resp.status_code == 200, resp.text
    assert resp.json()["releases"]


# --- versions ------------------------------------------------------------------


async def test__api__versions__before_any_check__lists_only_the_installed_one(
    test_app: AsyncClient,
) -> None:
    resp = await test_app.get("/api/v1/system/versions")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current"] == settings.get_app_version()
    assert body["checked_at"] is None
    # Установленная версия обязана быть в списке всегда: пользователь должен
    # видеть, где он находится, даже без единой удачной проверки фида.
    assert [v["version"] for v in body["versions"]] == [settings.get_app_version()]
    assert body["versions"][0]["installed"] is True
    assert body["versions"][0]["newer"] is False


async def test__api__versions__after_a_check__lists_everything_newest_first(
    app_with_newer_release: AsyncClient,
) -> None:
    await app_with_newer_release.post("/api/v1/system/check-updates")

    resp = await app_with_newer_release.get("/api/v1/system/versions")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    versions = [v["version"] for v in body["versions"]]
    assert versions[0] == "999.0.0"
    assert versions == sorted(versions, key=lambda v: [int(p) for p in v.split(".")], reverse=True)
    # Более ранние релизы тоже в списке — на них можно откатиться.
    assert {"0.0.2", "0.0.1"} <= set(versions)
    assert body["checked_at"]

    by_version = {v["version"]: v for v in body["versions"]}
    assert by_version["999.0.0"]["newer"] is True
    assert by_version["999.0.0"]["notes"] == ["Что-то новое"]
    assert by_version["0.0.1"]["newer"] is False
    assert by_version[settings.get_app_version()]["installed"] is True


async def test__api__versions__survives_a_restart(
    app_with_newer_release: AsyncClient,
    app_with_unreachable_feed: AsyncClient,
) -> None:
    # Оба приложения смотрят в один data_dir: список версий пережил перезапуск и
    # доступен, даже когда фид уже недоступен.
    await app_with_newer_release.post("/api/v1/system/check-updates")

    resp = await app_with_unreachable_feed.get("/api/v1/system/versions")

    assert resp.status_code == 200, resp.text
    assert "999.0.0" in [v["version"] for v in resp.json()["versions"]]
