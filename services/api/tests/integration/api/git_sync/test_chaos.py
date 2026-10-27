"""Сбои посреди синхронизации: отмена, обрыв, исчезнувший сервер, смерть процесса, неверный токен, старые данные.

Каждый тест ломает один шаг настоящего пути (выборку, применение, отправку) и проверяет одно: проект цел, ошибка
честная, фоновые git-процессы не остались, а следующая синхронизация доводит дело до конца и Студии сходятся.
Сервером служит настоящий `git http-backend` на 127.0.0.1 либо голый репозиторий file://; часы расписания и подмена
слоёв сети детерминированы, ожидание по настоящим часам только там, где ждём процесс ОС.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.core.git_sync.entities import CredentialStatus
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, IGitTransport
from hse_doc_studio.infra.git_sync.fetch_scheduler import GitFetchScheduler
from hse_doc_studio.infra.git_sync.merge_committer import GitMergeCommitter
from hse_doc_studio.use_cases.git_sync.fetch_all_remotes import FetchAllGitRemotesUC, FetchTickResult
from hse_doc_studio.use_cases.template_update.transaction import TemplateUpdateTransaction

from tests.fixtures.git_remote import BareRemote, GitHttpServer
from tests.integration.api.git_sync.studios import (
    ANNA,
    PROJECT_FILE,
    TRACKED_FILE,
    Studio,
    converge,
    error_body,
    share_project,
    when,
    with_line,
)
from tests.integration.api.signatures.test_detached_signatures import (
    _DOC,
    _SLOT,
    _attach,
    _enable_detached_slot,
    _freeze,
    _frozen_bytes,
    _project_with_pdf,
)
from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity

pytestmark = [pytest.mark.integration, pytest.mark.timeout(180)]

_posix_only = pytest.mark.skipif(os.name != "posix", reason="процессы проверяются через ps")


# --- общие приёмы -------------------------------------------------------------------------------------------------


def _processes_for(marker: str) -> list[str]:
    """Строки команд живых процессов git, которые ходят на сервер `marker` (хост:порт)."""
    listing = subprocess.run(  # noqa: S603 — фиксированная команда
        ["ps", "-axo", "command="],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    return [line for line in listing.splitlines() if marker in line and "git" in line]


async def _no_processes_left(marker: str, *, within_s: float = 10.0) -> bool:
    async with asyncio.timeout(within_s + 5):
        deadline = asyncio.get_running_loop().time() + within_s
        while _processes_for(marker):
            if asyncio.get_running_loop().time() > deadline:
                return False
            await asyncio.sleep(0.05)
    return True


async def _until(check: Callable[[], bool], *, timeout_s: float = 20.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not check():
            await asyncio.sleep(0.02)


async def _phase(studio: Studio, operation_id: str, phase: str) -> None:
    async def reached() -> bool:
        resp = await studio.client.get(f"/api/v1/git/operations/{operation_id}")
        return bool(resp.json()["phase"] == phase and resp.json()["status"] == "running")

    async with asyncio.timeout(20):
        while not await reached():
            await asyncio.sleep(0.02)


class HttpRemote:
    """Проект Анны, подключённый к `git http-backend` по токену."""

    def __init__(self, studio: Studio, server: GitHttpServer, bare: BareRemote, credential_id: str) -> None:
        self.studio = studio
        self.server = server
        self.bare = bare
        self.credential_id = credential_id

    @property
    def marker(self) -> str:
        return f"127.0.0.1:{self.server.port}"

    @property
    def url(self) -> str:
        return self.server.url("origin.git")


@pytest_asyncio.fixture
async def http_remote(
    anna: Studio, http_git_server_factory: Callable[..., GitHttpServer], monkeypatch: pytest.MonkeyPatch
) -> HttpRemote:
    monkeypatch.setattr(app_settings.git, "allow_insecure_http", True)
    server = http_git_server_factory()
    bare = server.create_repo("origin.git")
    await anna.create_project()
    anna.git("push", "--quiet", bare.url, "master:refs/heads/main")
    created = await anna.client.post(
        "/api/v1/git/credentials",
        json={"kind": "pat", "label": "Токен", "host": "127.0.0.1", "token": server.token},
    )
    assert created.status_code == 201, created.text
    credential_id = str(created.json()["id"])
    connected = await anna.client.put(
        anna.url("remote"),
        json={"url": server.url("origin.git"), "credential_id": credential_id, "insecure_http": True},
    )
    assert connected.status_code == 200, connected.text
    return HttpRemote(anna, server, bare, credential_id)


async def _hang_after_fetch(studio: Studio, monkeypatch: pytest.MonkeyPatch, server: GitHttpServer, mode: str) -> None:
    """Выборка проходит как есть, а после неё сервер переходит в `mode`: отказ ловит именно отправка."""
    transport = await studio.get(IGitTransport)
    original = transport.fetch
    broken = False

    async def fetch_then_break(*args: Any, **kwargs: Any) -> None:
        nonlocal broken
        await original(*args, **kwargs)
        # Один раз: повторная синхронизация после починки сервера идёт уже обычным путём.
        if not broken:
            broken = True
            server.mode = mode

    monkeypatch.setattr(transport, "fetch", fetch_then_break)


# --- отмена посреди сети -------------------------------------------------------------------------------------------


@_posix_only
@pytest.mark.parametrize("hung_phase", ["fetch", "push"])
async def test__chaos__cancel_while_the_server_hangs__git_is_killed_and_the_next_sync_finishes(
    http_remote: HttpRemote, monkeypatch: pytest.MonkeyPatch, hung_phase: str
) -> None:
    anna, server = http_remote.studio, http_remote.server
    await anna.put("notes/work.txt", "работа Анны\n")
    local = anna.head()
    before = http_remote.bare.head()
    if hung_phase == "fetch":
        server.mode = "hang"
    else:
        await _hang_after_fetch(anna, monkeypatch, server, "hang")
    requests_before = len(server.requests)

    started = await anna.start_sync()
    assert started.status_code == 202, started.text
    operation_id = started.json()["operation_id"]
    await _phase(anna, operation_id, hung_phase)
    await _until(lambda: len(server.requests) > requests_before)
    assert _processes_for(http_remote.marker), "git сидит на зависшем сервере"

    cancelled = await anna.client.post(f"/api/v1/git/operations/{operation_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    operation = await anna.wait(operation_id)

    assert operation.status == "cancelled"
    assert await _no_processes_left(http_remote.marker), _processes_for(http_remote.marker)
    # Проект и сервер не тронуты, состояние не застряло в «идёт синхронизация».
    assert anna.head() == local
    assert http_remote.bare.head() == before
    assert anna.dirty() == ""
    status = await anna.status()
    assert status.operation is None
    assert status.ui_state != "syncing"
    assert not (anna.folder / ".hse-studio" / "update" / "journal.json").exists()

    server.mode = "ok"
    result = await anna.sync_ok()

    assert result.outcome == "pushed"
    assert http_remote.bare.head() == anna.head() == local


@_posix_only
async def test__chaos__connection_dropped_in_the_middle_of_push__fails_honestly_and_retries(
    http_remote: HttpRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    anna, server = http_remote.studio, http_remote.server
    await anna.put("notes/work.txt", "работа Анны\n")
    local = anna.head()
    before = http_remote.bare.head()
    await _hang_after_fetch(anna, monkeypatch, server, "drop")

    operation = await anna.sync()

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code in ("offline", "git_error")
    assert await _no_processes_left(http_remote.marker)
    assert anna.head() == local
    assert http_remote.bare.head() == before
    status = await anna.status()
    assert status.health != "ok"
    assert status.last_error is not None
    assert status.last_error.code == operation.error.code
    assert status.operation is None

    server.mode = "ok"
    result = await anna.sync_ok()

    assert result.outcome == "pushed"
    assert http_remote.bare.head() == anna.head()
    healed = await anna.status()
    assert (healed.health, healed.last_error) == ("ok", None)


async def test__chaos__server_vanishes_between_fetch_and_push__fails_and_the_work_survives(
    anna: Studio, bare_remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await anna.create_project()
    await anna.connect(bare_remote)
    assert (await anna.sync_ok()).outcome == "pushed"
    await anna.put("notes/work.txt", "работа Анны\n")
    local = anna.head()
    before = bare_remote.head()
    gone = bare_remote.path.with_name("gone.git")
    transport = await anna.get(IGitTransport)
    original = transport.push

    async def vanish_then_push(*args: Any, **kwargs: Any) -> None:
        bare_remote.path.rename(gone)
        await original(*args, **kwargs)

    monkeypatch.setattr(transport, "push", vanish_then_push)

    operation = await anna.sync()

    assert operation.status == "failed"
    assert operation.error is not None
    assert anna.head() == local
    assert anna.dirty() == ""
    status = await anna.status()
    assert status.health != "ok"
    assert status.last_error is not None

    gone.rename(bare_remote.path)
    monkeypatch.undo()
    result = await anna.sync_ok()

    assert result.outcome == "pushed"
    assert bare_remote.head() == anna.head() != before
    assert (await anna.status()).health == "ok"


# --- отмена и смерть во время применения ------------------------------------------------------------------------


async def test__chaos__cancel_during_the_merge__is_refused_and_the_merge_completes(
    anna: Studio, boris: Studio, bare_remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await share_project(anna, boris, bare_remote)
    await anna.put("notes/anna.txt", "Анна\n")
    await boris.put("notes/boris.txt", "Борис\n")
    await anna.sync_ok()
    entered, release = threading.Event(), threading.Event()
    original = GitMergeCommitter.commit_merge

    def held(self: GitMergeCommitter, *args: Any, **kwargs: Any) -> str:
        entered.set()
        assert release.wait(30), "тест не отпустил применение"
        return original(self, *args, **kwargs)

    monkeypatch.setattr(GitMergeCommitter, "commit_merge", held)
    started = await boris.start_sync()
    operation_id = started.json()["operation_id"]
    await asyncio.to_thread(entered.wait, 20)
    await _phase(boris, operation_id, "merge")

    refused = await boris.client.post(f"/api/v1/git/operations/{operation_id}/cancel")

    assert refused.status_code == 409
    assert error_body(refused).code == "operation_not_cancellable"
    release.set()
    operation = await boris.wait(operation_id)
    assert operation.status == "succeeded", operation.error
    assert operation.result is not None
    assert operation.result.outcome == "merged"  # type: ignore[union-attr]
    assert (await anna.sync_ok()).outcome == "fast_forwarded"
    assert anna.tracked_content() == boris.tracked_content()


@pytest.mark.parametrize("dies", ["before_the_commit", "after_the_branch_moved"])
async def test__chaos__studio_killed_in_the_middle_of_the_merge__restart_repairs_it_and_both_converge(
    anna: Studio, boris: Studio, bare_remote: BareRemote, monkeypatch: pytest.MonkeyPatch, dies: str
) -> None:
    await share_project(anna, boris, bare_remote)
    await anna.put("notes/anna.txt", "Анна\n")
    await boris.put("notes/boris.txt", "Борис\n")
    await boris.sync_ok()
    local = anna.head()
    journal = anna.folder / ".hse-studio" / "update" / "journal.json"

    def killed(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("процесс убит")

    original_advance = GitMergeCommitter.advance_branch

    def moved_then_killed(self: GitMergeCommitter, *args: Any, **kwargs: Any) -> bool:
        original_advance(self, *args, **kwargs)
        raise RuntimeError("процесс убит после сдвига ветки")

    with monkeypatch.context() as patch:
        if dies == "before_the_commit":
            patch.setattr(GitMergeCommitter, "commit_merge", killed)
        else:
            patch.setattr(GitMergeCommitter, "advance_branch", moved_then_killed)
        # Смерть не успевает ни откатить файлы, ни убрать журнал: это делает только следующий запуск.
        patch.setattr(TemplateUpdateTransaction, "recover", lambda self, project, journal: False)
        operation = await anna.sync()

    assert operation.status == "failed"
    assert json.loads(journal.read_text(encoding="utf-8"))["kind"] == "sync"
    # До разбора журнала проект только для чтения, в том числе для самой синхронизации.
    detail = await anna.client.get(f"/api/v1/projects/{anna.id}")
    assert detail.json()["access"]["mode"] == "read_only"
    blocked = await anna.start_sync()
    assert blocked.status_code == 423

    await anna.restart()
    recovered = await anna.recover()

    assert [r.finalized for r in recovered.recovered] == [dies == "after_the_branch_moved"]
    assert not journal.exists()
    if dies == "before_the_commit":
        assert anna.head() == local
        assert not anna.file("notes/boris.txt").exists()
    else:
        assert anna.file("notes/boris.txt").exists()
    detail = await anna.client.get(f"/api/v1/projects/{anna.id}")
    assert detail.json()["access"]["mode"] == "full"
    assert anna.dirty() == ""

    await converge([anna, boris], lambda studio: "mine")

    assert anna.head() == boris.head() == bare_remote.head()
    assert anna.tracked_content() == boris.tracked_content()
    assert anna.read("notes/boris.txt") == "Борис\n"
    assert boris.read("notes/anna.txt") == "Анна\n"


# --- неверный токен при работающем расписании ---------------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


async def test__chaos__token_goes_bad__background_fetch_asks_once_stops_and_resumes_with_a_new_token(
    http_remote: HttpRemote,
) -> None:
    anna, server = http_remote.studio, http_remote.server
    credential_url = f"/api/v1/git/credentials/{http_remote.credential_id}"
    clock = Clock()
    ticks: list[FetchTickResult] = []
    waits = 0
    reached = asyncio.Event()
    wanted = 0

    async def run_tick() -> FetchTickResult:
        async with anna.container() as request:
            uc = await request.get(FetchAllGitRemotesUC)
            uc._clock = clock  # noqa: SLF001 — часы подменяются, чтобы срок проверялся без ожидания
            uc._fetch._clock = clock  # noqa: SLF001
            result = await uc.run_once()
        ticks.append(result)
        return result

    async def wait(_seconds: float) -> None:
        # Каждое «ожидание» между тиками это шесть часов на подменённых часах; настоящего ожидания нет.
        nonlocal waits
        waits += 1
        clock.advance(timedelta(hours=6))
        if len(ticks) >= wanted:
            reached.set()
            await asyncio.sleep(3600)
        await asyncio.sleep(0)

    async def run_ticks(count: int) -> None:
        nonlocal wanted
        wanted = len(ticks) + count
        reached.clear()
        scheduler = GitFetchScheduler(run_tick, tick_s=0, startup_delay_s=0, wait=wait)
        task = asyncio.create_task(scheduler.loop())
        try:
            async with asyncio.timeout(60):
                await reached.wait()
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def attempts() -> int:
        return len([r for r in server.requests if r.path.endswith("/info/refs?service=git-upload-pack")])

    # Токен испортился после подключения: сервер отвечает 401.
    patched = await anna.client.patch(credential_url, json={"token": "pat-revoked-0123456789"})
    assert patched.status_code == 200, patched.text

    await run_ticks(1)
    assert (ticks[-1].failed, ticks[-1].fetched) == (1, 0)
    asked = attempts()
    assert asked >= 1
    status = await anna.status()
    assert status.ui_state == "auth_failed"
    assert status.health == "unauthenticated"
    listed = await anna.client.get("/api/v1/git/credentials")
    assert [c["status"] for c in listed.json()] == ["auth_failed"]

    # Расписание крутится дальше, но сервер больше не беспокоят: после отказа в доступе опрос стоит.
    await run_ticks(5)
    assert attempts() == asked
    assert all(t.fetched == 0 and t.failed == 0 for t in ticks[1:])

    # Кнопка работает всегда и честно говорит то же самое.
    pressed = await anna.client.post(anna.url("fetch"))
    assert pressed.status_code == 200
    assert pressed.json()["ui_state"] == "auth_failed"
    manual = attempts()
    assert manual > asked

    # Человек заменил токен: расписание пробует снова и выздоравливает без других действий.
    fixed = await anna.client.patch(credential_url, json={"token": server.token})
    assert fixed.status_code == 200, fixed.text
    await run_ticks(2)
    assert [t.fetched for t in ticks[-2:]] == [1, 1]
    healed = await anna.status()
    assert (healed.ui_state, healed.health) == ("up_to_date", "ok")
    repo = await anna.get(IGitCredentialRepository)
    credential = repo.get(UUID(http_remote.credential_id))
    assert credential is not None
    assert credential.status is not CredentialStatus.auth_failed
    assert waits > 0


# --- подписанный документ едет вместе с проектом ------------------------------------------------------------------


async def test__chaos__frozen_pdf_and_its_signature__travel_through_the_remote_and_verify_after_clone(
    anna: Studio, boris: Studio, bare_remote: BareRemote
) -> None:
    (anna.root / "work").mkdir(parents=True)
    project_id, _ = await _project_with_pdf(anna.client, anna.root / "work" / "thesis")
    anna.project = (await anna.client.get(f"/api/v1/projects/{project_id}")).json()
    await _enable_detached_slot(anna.client, project_id)
    await _freeze(anna.client, project_id)
    frozen = await _frozen_bytes(anna.client, project_id)
    signature = make_detached_cms(make_identity("Петрова Анна Сергеевна"), frozen)
    attached = await _attach(anna.client, project_id, signature)
    assert attached.status_code == 200, attached.text
    assert attached.json()["signature"]["verdict"] == "valid"
    await anna.connect(bare_remote)

    pushed = await anna.sync_ok()
    assert pushed.outcome == "pushed"
    on_server = set(bare_remote.git("ls-tree", "-r", "--name-only", "main").splitlines())
    assert any(path.startswith(".hse-studio/frozen/") and path.endswith(".pdf") for path in on_server)
    assert PROJECT_FILE in on_server

    await boris.clone(bare_remote)

    # Тот же замороженный PDF байт в байт, подпись на месте и проверяется заново уже у Бориса.
    assert await _frozen_bytes(boris.client, project_id) == frozen
    state = (await boris.client.get(f"/api/v1/projects/{project_id}/signatures")).json()
    stored = state["detached"][_DOC][_SLOT]
    assert (stored["verdict"], stored["current"]) == ("valid", True)
    assert (
        state["frozen"][_DOC]["sha256"]
        == (await anna.client.get(f"/api/v1/projects/{project_id}/signatures")).json()["frozen"][_DOC]["sha256"]
    )
    assert (await boris.sync_ok()).outcome == "up_to_date"
    rechecked = await boris.client.post(f"/api/v1/projects/{project_id}/docs/{_DOC}/detached/{_SLOT}/recheck")
    assert rechecked.status_code == 200, rechecked.text
    assert rechecked.json()["signature"]["verdict"] == "valid"
    assert anna.tracked_content() == boris.tracked_content()
    # Перепроверка записала время проверки в состояние подписей: это обычная правка, она уходит и доходит до Анны.
    assert (await boris.sync_ok()).outcome == "pushed"
    assert (await anna.sync_ok()).outcome == "fast_forwarded"
    assert await _frozen_bytes(anna.client, project_id) == frozen


# --- старые данные открываются как раньше ---------------------------------------------------------------------------


def _age_the_project(studio: Studio) -> None:
    """Проект и хранилище, как их оставила Студия до синхронизации: без блока схемы, с прежним списком исключений."""
    data = studio.project_json()
    data.pop("schema", None)
    studio.write_project_json(data)
    exclude = studio.store / "info" / "exclude"
    newer = {".hse-studio/git", ".hse-studio/update/", ".hse-studio/backup/"}
    exclude.write_text(
        "".join(
            line for line in exclude.read_text(encoding="utf-8").splitlines(keepends=True) if line.strip() not in newer
        ),
        encoding="utf-8",
    )
    for state_file in (studio.store / "hse-sync.json",):
        state_file.unlink(missing_ok=True)
    studio.commit_dated("Состояние до синхронизации", when(1))


async def test__chaos__project_without_schema_block_and_an_old_store__open_edit_and_sync_like_any_other(
    anna: Studio, boris: Studio, bare_remote: BareRemote
) -> None:
    await anna.create_project()
    _age_the_project(anna)

    opened = await anna.client.get(f"/api/v1/projects/{anna.id}")
    assert opened.status_code == 200
    assert opened.json()["access"]["mode"] == "full"
    idle = await anna.status()
    assert (idle.connected, idle.ui_state) == (False, "no_remote")
    vcs = await anna.client.get(f"/api/v1/projects/{anna.id}/vcs/status")
    assert vcs.status_code == 200
    await anna.put(TRACKED_FILE, with_line(anna.read(TRACKED_FILE), 3, "% правка в старом проекте"))
    assert "% правка в старом проекте" in anna.git("show", "HEAD:" + TRACKED_FILE)

    await anna.connect(bare_remote)
    assert (await anna.sync_ok()).outcome == "pushed"
    exclude = (anna.store / "info" / "exclude").read_text(encoding="utf-8")
    assert ".hse-studio/update/" in exclude
    assert ".hse-studio/backup/" in exclude
    tree = anna.tracked()
    assert not any(path.startswith((".hse-studio/git", ".hse-studio/update", ".hse-studio/backup")) for path in tree)

    await boris.clone(bare_remote)
    assert (await boris.client.get(f"/api/v1/projects/{boris.id}")).json()["access"]["mode"] == "full"
    await boris.put("notes/boris.txt", "Борис\n")
    assert (await boris.sync_ok()).outcome == "pushed"
    assert (await anna.sync_ok()).outcome == "fast_forwarded"
    assert anna.tracked_content() == boris.tracked_content()
    assert anna.read("notes/boris.txt") == "Борис\n"
    assert ANNA[1] in anna.git("log", "-1", "--format=%ae", "--author", ANNA[1])
