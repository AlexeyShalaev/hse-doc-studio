"""Сходимость: в каком бы порядке Студии ни синхронизировались, они приходят к одному и тому же проекту.

Одни и те же расходящиеся правки (конфликты в тексте, в полях project.json и «изменил против удалил», чистое слияние
текста, бинарный файл, «сборка» с обеих сторон) прогоняются через разные расписания синхронизаций. Конфликты всегда
решаются в пользу Анны, поэтому исход известен заранее и одинаков для любого порядка: деревья совпадают друг с другом
и с ожидаемым. Время слияний бинарных файлов задано зафиксированными датами коммитов.
"""

from __future__ import annotations

import hashlib

import pytest

from tests.fixtures.git_remote import BareRemote
from tests.integration.api.git_sync.studios import (
    TRACKED_FILE,
    Studio,
    converge,
    share_project,
    when,
    with_line,
)

pytestmark = [pytest.mark.integration, pytest.mark.timeout(240)]

_ANNA_PNG = b"\x89PNG\r\n\x00anna-diagram"
_BORIS_PNG = b"\x89PNG\r\n\x00boris-diagram"
_INTRO_LINE = 3
_USAGE_LINE = 15
_DRAFT = "notes/draft.txt"

# Расписание: кто синхронизируется по очереди; «edit» это ещё одна правка Анны посреди расписания.
_SCHEDULES = {
    "anna-then-boris": ("A", "B"),
    "boris-then-anna": ("B", "A"),
    "alternating": ("A", "B", "A", "B"),
    "boris-twice-first": ("B", "B", "A"),
    "late-edit-between": ("A", "edit", "B"),
}


def _prefer(studio: Studio) -> str:
    """Конфликты решаются в пользу Анны: для неё это «моё», для Бориса «чужое»."""
    return "mine" if studio.name == "anna" else "theirs"


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()  # noqa: S324


async def _diverge(anna: Studio, boris: Studio) -> None:
    # Общее начало: черновик, который потом Анна правит, а Борис удаляет.
    anna.write(_DRAFT, "черновик\n")
    anna.commit_dated("Анна: черновик", when(1))
    assert (await anna.sync_ok()).outcome == "pushed"
    assert (await boris.sync_ok()).outcome == "fast_forwarded"

    await anna.put(TRACKED_FILE, with_line(anna.read(TRACKED_FILE), _INTRO_LINE, "% Анна: введение"))
    anna.write(_DRAFT, "черновик\nстрока Анны\n")
    anna.write("notes/anna.txt", "заметка Анны\n")
    anna.write("figures/diagram.png", _ANNA_PNG)
    anna.write("notes/agreed.txt", "одинаково\n")
    renamed = await anna.client.patch(f"/api/v1/projects/{anna.id}", json={"name": "Название Анны"})
    assert renamed.status_code == 200, renamed.text
    data = anna.project_json()
    data["documents"][0]["last_compile_id"] = "11111111-1111-4111-8111-111111111111"
    data["updated_at"] = "2030-01-02T10:00:00Z"
    anna.write_project_json(data)
    anna.commit_dated("Анна: правки", when(2))

    boris.write(TRACKED_FILE, with_line(boris.read(TRACKED_FILE), _INTRO_LINE, "% Борис: введение"))
    boris.write(TRACKED_FILE, with_line(boris.read(TRACKED_FILE), _USAGE_LINE, "% Борис: пояснение"))
    boris.file(_DRAFT).unlink()
    boris.write("notes/boris.txt", "заметка Бориса\n")
    boris.write("figures/diagram.png", _BORIS_PNG)
    boris.write("notes/agreed.txt", "одинаково\n")
    renamed = await boris.client.patch(
        f"/api/v1/projects/{boris.id}", json={"name": "Название Бориса", "meta": {"specialization": "Данные"}}
    )
    assert renamed.status_code == 200, renamed.text
    data = boris.project_json()
    data["documents"][0]["last_compile_id"] = "22222222-2222-4222-8222-222222222222"
    data["updated_at"] = "2030-01-03T10:00:00Z"
    boris.write_project_json(data)
    boris.commit_dated("Борис: правки", when(3))


def _expect_the_agreed_project(studio: Studio) -> None:
    text = studio.read(TRACKED_FILE).splitlines()
    assert text[_INTRO_LINE - 1] == "% Анна: введение"
    assert text[_USAGE_LINE - 1] == "% Борис: пояснение"
    assert studio.read(_DRAFT) == "черновик\nстрока Анны\n"
    assert studio.read("notes/anna.txt") == "заметка Анны\n"
    assert studio.read("notes/boris.txt") == "заметка Бориса\n"
    assert studio.read("notes/agreed.txt") == "одинаково\n"
    # Бинарный файл: побеждает более поздний (Бориса), проигравший лежит рядом под именем по его содержимому.
    assert studio.file("figures/diagram.png").read_bytes() == _BORIS_PNG
    copy = f"figures/diagram.conflict-{_blob_sha(_ANNA_PNG)[:7]}.png"
    assert studio.file(copy).read_bytes() == _ANNA_PNG
    assert sorted(p.name for p in studio.file("figures").iterdir()) == sorted(["diagram.png", copy.split("/")[1]])
    project = studio.project_json()
    assert project["name"] == "Название Анны"
    assert project["meta"]["specialization"] == "Данные"
    assert project["updated_at"].startswith("2030-01-03")
    assert studio.dirty() == ""


@pytest.mark.parametrize("schedule", _SCHEDULES.values(), ids=_SCHEDULES.keys())
async def test__convergence__any_sync_order__gives_the_same_project(
    anna: Studio, boris: Studio, bare_remote: BareRemote, schedule: tuple[str, ...]
) -> None:
    await share_project(anna, boris, bare_remote)
    await _diverge(anna, boris)
    studios = {"A": anna, "B": boris}
    late = False

    for step in schedule:
        if step == "edit":
            await anna.put("notes/anna-late.txt", "позднее\n")
            late = True
        else:
            await studios[step].sync_deciding(_prefer(studios[step]))
    await converge([anna, boris], _prefer)

    # Конфликты возникли ровно один раз: у того, кто пришёл вторым.
    assert anna.stopped_on_conflicts + boris.stopped_on_conflicts == 1
    assert anna.head() == boris.head() == bare_remote.head()
    for studio in (anna, boris):
        _expect_the_agreed_project(studio)
        assert (
            (studio.read("notes/anna-late.txt") == "позднее\n")
            if late
            else not studio.file("notes/anna-late.txt").exists()
        )
    assert anna.tracked_content() == boris.tracked_content()
    # Сошлись и не плодят коммитов: ещё круг синхронизаций ничего не меняет.
    head, count = anna.head(), anna.commit_count()
    for studio in (boris, anna):
        assert (await studio.sync_ok()).outcome == "up_to_date"
    assert (anna.head(), anna.commit_count(), boris.head()) == (head, count, head)
    for studio in (anna, boris):
        assert (await studio.status()).pending is None
