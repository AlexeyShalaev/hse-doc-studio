"""Две Студии и один удалённый репозиторий: весь путь коллективной работы через настоящий API.

Анна создаёт проект и подключает пустой репозиторий, Борис клонирует его. Дальше оба правят свои места: один и тот же
файл в разных строках, разные файлы, бинарный файл, поля project.json и «сборку». Студии синхронизируются в разном
порядке, конфликты решаются через API. В конце деревья совпадают, история хранит каждый снимок с настоящим автором, а
повторная синхронизация без правок не создаёт ни одного коммита. У Студий разные data_dir, профили и папки, общего у
них только голый репозиторий file://; сети нет, git настоящий.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hse_doc_studio.api.schemas.git_sync import SyncResult

from tests.fixtures.git_remote import BareRemote
from tests.integration.api.git_sync.studios import (
    ANNA,
    BORIS,
    PROJECT_FILE,
    TRACKED_FILE,
    Studio,
    share_project,
    when,
    with_line,
)

# Каждый тест это две Студии и десятки настоящих запусков git: на загруженной машине 30 секунд по умолчанию мало.
pytestmark = [pytest.mark.integration, pytest.mark.timeout(180)]

_ANNA_PNG = b"\x89PNG\r\n\x00anna-diagram"
_BORIS_PNG = b"\x89PNG\r\n\x00boris-diagram"
_ANNA_COMPILE = "11111111-1111-4111-8111-111111111111"
_BORIS_COMPILE = "22222222-2222-4222-8222-222222222222"
_AUTOSAVE = "Автосохранение перед синхронизацией"
_COPY = re.compile(r"^figures/diagram\.conflict-[0-9a-f]{7}\.png$")
# Строка комментария в начале шаблона ВКР: правки Анны и Бориса в ней сталкиваются, в строках вдали друг от друга нет.
_INTRO_LINE = 3
_USAGE_LINE = 15


def _usage_line(studio: Studio) -> str:
    return studio.read(TRACKED_FILE).splitlines()[_USAGE_LINE - 1]


async def _edit_apart(anna: Studio, boris: Studio) -> None:
    """Каждый правит своё: ни одного пересечения, кроме тех, что слияние обязано решить само."""
    # Анна: строка введения и заметка сохраняются как в редакторе (каждое сохранение коммит правки), потом название
    # проекта, схема с зафиксированной датой и «сборка».
    await anna.put(TRACKED_FILE, with_line(anna.read(TRACKED_FILE), _INTRO_LINE, "% Анна: введение переписано"))
    await anna.put("notes/anna.txt", "заметка Анны\n")
    renamed = await anna.client.patch(f"/api/v1/projects/{anna.id}", json={"name": "Диплом: версия Анны"})
    assert renamed.status_code == 200, renamed.text
    anna.write("figures/diagram.png", _ANNA_PNG)
    anna.write("notes/agreed.txt", "одинаково у обоих\n")
    data = anna.project_json()
    data["documents"][0]["last_compile_id"] = _ANNA_COMPILE
    data["updated_at"] = "2030-01-02T10:00:00Z"
    anna.write_project_json(data)
    anna.commit_dated("Анна: схема, заметка и сборка", when(2))

    # Борис: его схема новее Анниной, поэтому именно его файл должен победить.
    await boris.put("notes/boris-saved.txt", "сохранено в редакторе\n")
    boris.write("figures/diagram.png", _BORIS_PNG)
    boris.write("notes/agreed.txt", "одинаково у обоих\n")
    data = boris.project_json()
    data["documents"][0]["last_compile_id"] = _BORIS_COMPILE
    data["updated_at"] = "2030-01-03T10:00:00Z"
    boris.write_project_json(data)
    boris.commit_dated("Борис: схема и сборка", when(3))
    # Дальше правки Бориса остаются несохранёнными: их снимет сама синхронизация.
    boris.write(TRACKED_FILE, with_line(boris.read(TRACKED_FILE), _USAGE_LINE, "% Борис: пояснение дописано"))
    boris.write("notes/boris.txt", "заметка Бориса\n")
    specialized = await boris.client.patch(f"/api/v1/projects/{boris.id}", json={"meta": {"specialization": "Данные"}})
    assert specialized.status_code == 200, specialized.text
    data = boris.project_json()
    data["updated_at"] = "2030-01-03T11:00:00Z"
    boris.write_project_json(data)
    assert boris.dirty() != ""


def _authors(studio: Studio, *revs: str) -> dict[str, tuple[str, str]]:
    """sha -> (имя, почта) автора для каждого коммита, достижимого из `revs`."""
    log = studio.git("log", "--format=%H|%an|%ae", *revs)
    return {sha: (name, email) for sha, name, email in (line.split("|") for line in log.splitlines())}


async def test__two_studios__edits_in_every_corner__converge_to_one_project(
    anna: Studio, boris: Studio, bare_remote: BareRemote
) -> None:
    await share_project(anna, boris, bare_remote)
    await _edit_apart(anna, boris)
    anna_before = set(_authors(anna, "HEAD"))
    boris_before = set(_authors(boris, "HEAD"))

    # Анна отправляет первой, Борис получает и сливает, Анна перематывается на его слияние.
    first = await anna.sync_ok()
    assert first.outcome == "pushed"
    assert bare_remote.head() == anna.head()

    second = await boris.sync_ok()
    assert second.outcome == "merged", second
    assert second.conflicts is None
    assert second.warnings == []
    assert second.pulled_commits >= 2
    assert second.merge_commit is not None
    assert bare_remote.head() == second.merge_commit == boris.head()
    binary = [change for change in second.auto if change.action == "binary_newest"]
    assert len(binary) == 1
    assert binary[0].path == "figures/diagram.png"
    assert binary[0].copy_path is not None
    assert _COPY.match(binary[0].copy_path)

    third = await anna.sync_ok()
    assert third.outcome == "fast_forwarded"
    assert third.merge_commit is None
    assert anna.head() == boris.head() == bare_remote.head()

    # Деревья совпали, рабочие папки чисты, а каждая сторона видит правки другой.
    assert anna.tracked_content() == boris.tracked_content()
    assert anna.dirty() == boris.dirty() == ""
    for studio in (anna, boris):
        text = studio.read(TRACKED_FILE).splitlines()
        assert text[_INTRO_LINE - 1] == "% Анна: введение переписано"
        assert text[_USAGE_LINE - 1] == "% Борис: пояснение дописано"
        assert studio.read("notes/anna.txt") == "заметка Анны\n"
        assert studio.read("notes/boris.txt") == "заметка Бориса\n"
        assert studio.read("notes/boris-saved.txt") == "сохранено в редакторе\n"
        assert studio.read("notes/agreed.txt") == "одинаково у обоих\n"
        # Бинарный файл: побеждает более поздний (Бориса), проигравший лежит рядом под предсказуемым именем.
        assert studio.file("figures/diagram.png").read_bytes() == _BORIS_PNG
        assert studio.file(binary[0].copy_path).read_bytes() == _ANNA_PNG
        project = studio.project_json()
        assert project["name"] == "Диплом: версия Анны"
        assert project["meta"]["specialization"] == "Данные"
        assert project["meta"]["year"], "остальные поля meta не потеряны"
        assert project["updated_at"].startswith("2030-01-03T11")

    # «Сборка» Бориса на его же машине осталась его: правило local_only при настоящем слиянии.
    assert _boris_compile(boris) == _BORIS_COMPILE

    # Слияние от имени Бориса, снимки и коммиты сохранились целиком и с настоящими авторами.
    merge = boris.git("log", "-1", "--format=%an|%ae|%B", second.merge_commit)
    assert merge.startswith(f"{BORIS[0]}|{BORIS[1]}|")
    assert "Hse-Kind: sync" in merge
    assert "Hse-Sync: " in merge
    authors = _authors(anna, "HEAD")
    assert anna_before <= set(authors)
    assert boris_before <= set(authors)
    assert _authors(boris, "HEAD") == authors
    saved = [sha for sha, subject in _subjects(anna).items() if subject == _AUTOSAVE]
    assert saved, "автосохранение Бориса перед синхронизацией есть в истории"
    assert {authors[sha] for sha in saved} == {BORIS}
    subjects = _subjects(anna)
    assert {subjects[sha] for sha in authors if authors[sha] == ANNA} >= {
        f"Правка: {TRACKED_FILE}",
        "Правка: notes/anna.txt",
        "Анна: схема, заметка и сборка",
    }
    assert {subjects[sha] for sha in authors if authors[sha] == BORIS} >= {
        "Правка: notes/boris-saved.txt",
        "Борис: схема и сборка",
        _AUTOSAVE,
    }

    # Та же история, как её видит интерфейс: оба автора, всё уже отправлено, у слияния два родителя.
    for studio in (anna, boris):
        commits = await studio.history()
        assert {c["author_email"] for c in commits} >= {ANNA[1], BORIS[1]}
        assert {c["sync"] for c in commits} == {"pushed"}
        merges = [c for c in commits if c["is_merge"]]
        assert [c["id"] for c in merges] == [second.merge_commit]
        assert len(merges[0]["parents"]) == 2

    # Повторная синхронизация без правок ничего не создаёт ни у кого.
    head, count = anna.head(), anna.commit_count()
    for studio in (boris, anna, boris, anna):
        again = await studio.sync_ok()
        assert again.outcome == "up_to_date"
        assert (again.pulled_commits, again.pushed_commits, again.merge_commit) == (0, 0, None)
    assert (anna.head(), anna.commit_count()) == (head, count)
    assert boris.head() == bare_remote.head() == head
    status = await boris.status()
    assert (status.ui_state, status.ahead, status.behind) == ("up_to_date", 0, 0)


def _boris_compile(boris: Studio) -> str | None:
    value = boris.project_json()["documents"][0]["last_compile_id"]
    return value if isinstance(value, str) else None


def _subjects(studio: Studio) -> dict[str, str]:
    log = studio.git("log", "--format=%H|%s")
    return dict(line.split("|", 1) for line in log.splitlines())


async def test__two_studios__other_order__boris_first_gives_the_same_result(
    anna: Studio, boris: Studio, bare_remote: BareRemote
) -> None:
    await share_project(anna, boris, bare_remote)
    await _edit_apart(anna, boris)

    assert (await boris.sync_ok()).outcome == "pushed"
    merged = await anna.sync_ok()
    assert merged.outcome == "merged"
    assert (await boris.sync_ok()).outcome == "fast_forwarded"

    assert anna.tracked_content() == boris.tracked_content()
    assert anna.head() == boris.head() == bare_remote.head()
    assert anna.dirty() == boris.dirty() == ""
    # Теперь сливала Анна: слияние подписано ею, а её «сборка» осталась её.
    assert anna.git("log", "-1", "--format=%ae", anna.head()) == ANNA[1]
    assert anna.project_json()["documents"][0]["last_compile_id"] == _ANNA_COMPILE
    for studio in (anna, boris):
        assert studio.file("figures/diagram.png").read_bytes() == _BORIS_PNG


async def test__two_studios__same_place_conflicts__are_resolved_through_the_api_and_reach_the_colleague(
    anna: Studio, boris: Studio, bare_remote: BareRemote
) -> None:
    await share_project(anna, boris, bare_remote)
    await anna.put(TRACKED_FILE, with_line(anna.read(TRACKED_FILE), _INTRO_LINE, "% Анна: введение"))
    renamed = await anna.client.patch(f"/api/v1/projects/{anna.id}", json={"name": "Название Анны"})
    assert renamed.status_code == 200
    await boris.put(TRACKED_FILE, with_line(boris.read(TRACKED_FILE), _INTRO_LINE, "% Борис: введение"))
    renamed = await boris.client.patch(f"/api/v1/projects/{boris.id}", json={"name": "Название Бориса"})
    assert renamed.status_code == 200
    await boris.put("notes/boris.txt", "заметка Бориса\n")
    await anna.sync_ok()

    stopped = await boris.sync_ok()

    assert stopped.outcome == "conflicts"
    assert stopped.conflicts is not None
    assert (stopped.conflicts.files_total, stopped.conflicts.files_open) == (2, 2)
    assert bare_remote.head() == anna.head()
    # Пока конфликты не решены, рабочая папка Бориса не тронута: ни маркеров, ни чужих файлов.
    assert boris.read(TRACKED_FILE).splitlines()[_INTRO_LINE - 1] == "% Борис: введение"
    assert "hse:ours" not in boris.read(TRACKED_FILE)
    status = await boris.status()
    assert (status.ui_state, status.pending is not None) == ("conflicts", True)
    session = await boris.session()
    assert {f.path for f in session.files if f.action == "conflict"} == {TRACKED_FILE, PROJECT_FILE}
    # Правка, не связанная с конфликтом, пока открыт экран, сессию не сбивает.
    boris.write("notes/while-open.txt", "написано при открытом экране\n")
    assert (await boris.session()).fingerprint == session.fingerprint

    # Введение: побеждает Анна (чужая сторона для Бориса), название: побеждает Борис (его сторона).
    solved = await boris.resolve_all("theirs", {PROJECT_FILE: "mine"})

    assert solved.outcome == "merged"
    assert solved.pushed_commits >= 1
    assert bare_remote.head() == boris.head()
    assert boris.read(TRACKED_FILE).splitlines()[_INTRO_LINE - 1] == "% Анна: введение"
    assert boris.project_json()["name"] == "Название Бориса"
    assert (await boris.status()).pending is None

    received = await anna.sync_ok()

    assert received.outcome == "fast_forwarded"
    assert anna.read(TRACKED_FILE).splitlines()[_INTRO_LINE - 1] == "% Анна: введение"
    assert anna.project_json()["name"] == "Название Бориса"
    assert anna.read("notes/boris.txt") == "заметка Бориса\n"
    assert anna.read("notes/while-open.txt") == "написано при открытом экране\n"
    assert anna.tracked_content() == boris.tracked_content()
    assert anna.dirty() == boris.dirty() == ""
    for studio in (anna, boris):
        assert (await studio.sync_ok()).outcome == "up_to_date"


async def test__two_studios__abort_of_the_merge__leaves_both_projects_as_they_were(
    anna: Studio, boris: Studio, bare_remote: BareRemote
) -> None:
    await share_project(anna, boris, bare_remote)
    await anna.put(TRACKED_FILE, with_line(anna.read(TRACKED_FILE), _INTRO_LINE, "% Анна: введение"))
    await boris.put(TRACKED_FILE, with_line(boris.read(TRACKED_FILE), _INTRO_LINE, "% Борис: введение"))
    await anna.sync_ok()
    assert (await boris.sync_ok()).outcome == "conflicts"
    mine = boris.read(TRACKED_FILE)
    remote_head = bare_remote.head()

    aborted = await boris.client.delete(boris.url("conflicts"))

    assert aborted.status_code == 200, aborted.text
    assert boris.read(TRACKED_FILE) == mine
    assert bare_remote.head() == remote_head
    assert (await boris.status()).pending is None
    # Отказ не мешает начать заново: следующая синхронизация строит новую сессию с тем же итогом.
    assert (await boris.sync_ok()).outcome == "conflicts"
    solved = await boris.resolve_all("mine")
    assert solved.outcome == "merged"
    assert (await anna.sync_ok()).outcome == "fast_forwarded"
    assert anna.read(TRACKED_FILE).splitlines()[_INTRO_LINE - 1] == "% Борис: введение"


async def test__two_studios__alternating_edits__stay_linear_and_idle_syncs_add_nothing(
    anna: Studio, boris: Studio, bare_remote: BareRemote
) -> None:
    await share_project(anna, boris, bare_remote)
    studios = [anna, boris]
    commits = anna.commit_count()
    for turn in range(4):
        author, other = studios[turn % 2], studios[(turn + 1) % 2]
        await author.put(f"notes/turn-{turn}.txt", f"правка {turn} от {author.name}\n")

        pushed: SyncResult = await author.sync_ok()
        received = await other.sync_ok()

        assert pushed.outcome == "pushed"
        assert received.outcome == "fast_forwarded"
        commits += 1
        assert author.commit_count() == other.commit_count() == commits
        assert (await author.sync_ok()).outcome == "up_to_date"
        assert (await other.sync_ok()).outcome == "up_to_date"
        assert author.commit_count() == other.commit_count() == commits
    # Никто не сливал: история одной линией, слияний нет, у каждого коммита один родитель.
    assert anna.git("rev-list", "--merges", "--count", "HEAD") == "0"
    assert anna.tracked_content() == boris.tracked_content()
    edits = [c for c in await boris.history() if c["message"].startswith("Правка: notes/turn-")]
    assert len(edits) == 4
    assert {c["author_email"] for c in edits} == {ANNA[1], BORIS[1]}


async def test__two_studios__cloned_project_is_the_same_project_with_its_own_folder(
    anna: Studio, boris: Studio, bare_remote: BareRemote, tmp_path: Path
) -> None:
    await share_project(anna, boris, bare_remote)

    assert boris.folder != anna.folder
    assert boris.folder.is_relative_to(tmp_path / "boris")
    assert anna.folder.is_relative_to(tmp_path / "anna")
    assert (boris.folder / ".hse-studio" / "git" / "HEAD").exists()
    assert not (boris.folder / ".git").exists()
    assert anna.tracked_content() == boris.tracked_content()
    shown = await boris.client.get(f"/api/v1/projects/{boris.id}")
    assert shown.json()["access"]["mode"] == "full"
    status = await boris.status()
    assert (status.connected, status.ui_state, status.profile_ok) == (True, "up_to_date", True)
