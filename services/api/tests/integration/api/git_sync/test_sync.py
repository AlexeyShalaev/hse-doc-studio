"""Синхронизация проекта через настоящий API: снимок, выборка, перемотка, слияние, отправка, конфликты.

Удалённый репозиторий локальный голый (file://), «другая Студия» это обычная рабочая копия, которая коммитит и
отправляет в него напрямую. Проект и его хранилище настоящие, git настоящий, сети нет.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.schemas.git_sync import GitErrorBody, GitStatusResponse, OperationResponse
from hse_doc_studio.core.git_sync.entities import OperationKind, OperationPhase
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry, IGitTransport
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.use_cases.git_sync import sync_project
from hse_doc_studio.use_cases.template_update.recover_template_updates import RecoverTemplateUpdatesUC
from hse_doc_studio.use_cases.template_update.transaction import TemplateUpdateTransaction
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.git_remote import BareRemote, make_bare_remote, run_git
from tests.integration.api.vcs.conftest import TRACKED_FILE, create_project, edit_tracked_file

_PROFILE = {"name": "Анна Петрова", "email": "a.petrova@edu.hse.ru"}
_PEER = ("Борис Сидоров", "b.sidorov@edu.hse.ru")
_COMPILE_MINE = "11111111-1111-4111-8111-111111111111"
_COMPILE_THEIRS = "22222222-2222-4222-8222-222222222222"


@dataclass
class Stack:
    client: AsyncClient
    container: Any
    tmp_path: Path

    async def get[T](self, kind: type[T]) -> T:
        return await self.container.get(kind)  # type: ignore[no-any-return]


@pytest_asyncio.fixture
async def stack(tmp_path: Path) -> AsyncIterator[Stack]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir)
    app = create_test_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put("/api/v1/profile", json=_PROFILE)
        assert resp.status_code == 200, resp.text
        yield Stack(client, container, tmp_path)
    await container.close()


@pytest.fixture
def remote(tmp_path: Path) -> BareRemote:
    return make_bare_remote(tmp_path / "remotes" / "origin.git")


@pytest_asyncio.fixture
async def project(stack: Stack) -> dict[str, Any]:
    return await create_project(stack.client, stack.tmp_path / "proj")


class Peer:
    """Другая Студия: обычная рабочая копия, которая коммитит в тот же удалённый репозиторий."""

    def __init__(self, path: Path, remote: BareRemote) -> None:
        self.path = path
        self.remote = remote
        run_git("clone", "--quiet", "-b", "main", remote.url, str(path))

    def git(self, *args: str) -> str:
        identity = ["-c", f"user.name={_PEER[0]}", "-c", f"user.email={_PEER[1]}"]
        return run_git(*identity, *args, cwd=self.path)

    def write(self, rel: str, content: str | bytes) -> None:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())

    def read(self, rel: str) -> str:
        return (self.path / rel).read_text(encoding="utf-8")

    def commit_push(self, message: str = "peer edit") -> str:
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", message)
        self.git("push", "--quiet", self.remote.url, "HEAD:refs/heads/main")
        return self.git("rev-parse", "HEAD")

    def pull(self) -> None:
        self.git("pull", "--quiet", "--no-rebase", "--no-edit", self.remote.url, "main")


def _store(project: dict[str, Any]) -> Path:
    return Path(project["folder"]) / ".hse-studio" / "git"


def _git(project: dict[str, Any], *args: str, check: bool = True) -> str:
    return run_git(*args, git_dir=_store(project), work_tree=Path(project["folder"]), check=check)


def _file(project: dict[str, Any], rel: str) -> Path:
    return Path(project["folder"]) / rel


def _state(project: dict[str, Any]) -> dict[str, Any]:
    return json.loads((_store(project) / "hse-sync.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


async def _connect_in_sync(stack: Stack, project: dict[str, Any], remote: BareRemote) -> Peer:
    """Проект опубликован, подключён, и рядом стоит вторая Студия с той же историей."""
    _git(project, "push", "--quiet", remote.url, "master:refs/heads/main")
    resp = await stack.client.put(
        f"/api/v1/projects/{project['id']}/git/remote", json={"url": remote.url, "credential_id": None}
    )
    assert resp.status_code == 200, resp.text
    return Peer(stack.tmp_path / "peer", remote)


async def _status(stack: Stack, project: dict[str, Any]) -> GitStatusResponse:
    resp = await stack.client.get(f"/api/v1/projects/{project['id']}/git")
    assert resp.status_code == 200, resp.text
    return GitStatusResponse.model_validate(resp.json())


async def _start(stack: Stack, project: dict[str, Any]) -> Any:
    return await stack.client.post(f"/api/v1/projects/{project['id']}/git/sync", json={})


async def _wait(stack: Stack, operation_id: str, *, timeout: float = 30.0) -> OperationResponse:
    async with asyncio.timeout(timeout):
        while True:
            resp = await stack.client.get(f"/api/v1/git/operations/{operation_id}")
            assert resp.status_code == 200, resp.text
            operation = OperationResponse.model_validate(resp.json())
            if operation.status != "running":
                return operation
            await asyncio.sleep(0.02)


async def _sync(stack: Stack, project: dict[str, Any]) -> OperationResponse:
    started = await _start(stack, project)
    assert started.status_code == 202, started.text
    return await _wait(stack, started.json()["operation_id"])


async def _sync_ok(stack: Stack, project: dict[str, Any]) -> Any:
    operation = await _sync(stack, project)
    assert operation.status == "succeeded", operation.error
    assert operation.result is not None
    return operation.result


async def _recover(stack: Stack) -> Any:
    """То, что Студия делает при старте: разобрать прерванные журналы."""
    async with stack.container() as request:
        return await (await request.get(RecoverTemplateUpdatesUC)).execute()


def _error(resp: Any) -> GitErrorBody:
    return GitErrorBody.model_validate(resp.json())


def _snapshot(project: dict[str, Any], marker: str) -> str:
    edit_tracked_file(project, marker)
    _git(project, "add", "-A")
    _git(project, "-c", "user.name=Test", "-c", "user.email=t@test.local", "commit", "--quiet", "-m", marker)
    return _git(project, "rev-parse", "HEAD")


# --- чистые случаи: только мы, только они, обе стороны -----------------------------------------------------------


async def test__sync__ahead_only__pushes_and_reports_pushed(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect_in_sync(stack, project, remote)
    local = _snapshot(project, "local work")

    result = await _sync_ok(stack, project)

    assert result.outcome == "pushed"
    assert result.pushed_commits >= 1
    assert result.pulled_commits == 0
    assert remote.head() == local == _git(project, "rev-parse", "master")
    status = await _status(stack, project)
    assert status.ui_state == "up_to_date"
    assert status.last_sync is not None
    assert status.last_sync.outcome == "pushed"
    assert status.operation is None


async def test__sync__unsaved_edit__is_snapshotted_and_pushed(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect_in_sync(stack, project, remote)
    edit_tracked_file(project, "typed but never saved")

    result = await _sync_ok(stack, project)

    assert result.outcome == "pushed"
    assert remote.head() == _git(project, "rev-parse", "master")
    assert "typed but never saved" in remote.git("show", f"main:{TRACKED_FILE}")
    assert _git(project, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""


async def test__sync__nothing_to_do__is_up_to_date(stack: Stack, project: dict[str, Any], remote: BareRemote) -> None:
    await _connect_in_sync(stack, project, remote)
    before = remote.head()

    result = await _sync_ok(stack, project)

    assert result.outcome == "up_to_date"
    assert (result.pulled_commits, result.pushed_commits, result.merge_commit) == (0, 0, None)
    assert remote.head() == before


async def test__sync__first_push_to_empty_remote(stack: Stack, project: dict[str, Any], remote: BareRemote) -> None:
    resp = await stack.client.put(
        f"/api/v1/projects/{project['id']}/git/remote", json={"url": remote.url, "credential_id": None}
    )
    assert resp.status_code == 200, resp.text
    assert remote.head() is None

    result = await _sync_ok(stack, project)

    assert result.outcome == "pushed"
    assert remote.head() == _git(project, "rev-parse", "master")
    assert _state(project)["remote_empty"] is False
    status = await _status(stack, project)
    assert (status.ui_state, status.relation) == ("up_to_date", "in_sync")


async def test__sync__behind_only__fast_forwards_without_new_commit(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    before = _git(project, "rev-parse", "master")
    peer.write("notes/from-peer.txt", "hello from peer\n")
    theirs = peer.commit_push("peer adds a note")

    result = await _sync_ok(stack, project)

    assert result.outcome == "fast_forwarded"
    assert result.pulled_commits == 1
    assert result.merge_commit is None
    assert _git(project, "rev-parse", "master") == theirs
    assert _git(project, "rev-parse", "master^") == before
    assert _file(project, "notes/from-peer.txt").read_text(encoding="utf-8") == "hello from peer\n"
    assert [(a.path, a.action) for a in result.auto] == [("notes/from-peer.txt", "take_theirs")]
    assert _git(project, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""


async def test__sync__fast_forward_deletes_files_removed_upstream(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    peer.write("scratch.txt", "x\n")
    peer.commit_push("add scratch")
    await _sync_ok(stack, project)
    assert _file(project, "scratch.txt").exists()
    peer.pull()
    (peer.path / "scratch.txt").unlink()
    peer.commit_push("remove scratch")

    result = await _sync_ok(stack, project)

    assert result.outcome == "fast_forwarded"
    assert not _file(project, "scratch.txt").exists()


async def test__sync__diverged_clean__merge_commit_with_trailers_and_profile_author(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    ours = _snapshot(project, "local line")
    peer.write("notes/peer-only.txt", "peer file\n")
    theirs = peer.commit_push("peer file")

    result = await _sync_ok(stack, project)

    assert result.outcome == "merged"
    assert result.pulled_commits == 1
    assert result.pushed_commits >= 1
    merge = result.merge_commit
    assert merge is not None
    assert _git(project, "rev-list", "--parents", "-n1", merge).split() == [merge, ours, theirs]
    body = _git(project, "log", "-1", "--format=%B", merge)
    assert "Hse-Kind: sync" in body
    assert "Hse-Sync: " in body
    assert _git(project, "log", "-1", "--format=%an <%ae>", merge) == "Анна Петрова <a.petrova@edu.hse.ru>"
    assert remote.head() == merge == _git(project, "rev-parse", "master")
    assert _file(project, "notes/peer-only.txt").read_text(encoding="utf-8") == "peer file\n"
    assert "local line" in _file(project, TRACKED_FILE).read_text(encoding="utf-8")
    assert _git(project, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""
    assert not (_store(project).parent / "update" / "journal.json").exists()
    peer.pull()
    assert peer.read("notes/peer-only.txt") == "peer file\n"
    assert "local line" in peer.read(TRACKED_FILE)


async def test__sync__same_file_different_places__text_merges_cleanly(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    original = peer.read(TRACKED_FILE)
    peer.write(TRACKED_FILE, "% peer header\n" + original)
    peer.commit_push("peer edits the top")
    _snapshot(project, "mine at the bottom")

    result = await _sync_ok(stack, project)

    assert result.outcome == "merged"
    merged = _file(project, TRACKED_FILE).read_text(encoding="utf-8")
    assert merged.startswith("% peer header\n")
    assert "% mine at the bottom" in merged
    assert [a.action for a in result.auto if a.path == TRACKED_FILE] == ["merged"]


async def test__sync__compiles_on_both_sides__project_json_merges_without_conflict(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    project_file = ".hse-studio/project.json"
    mine = json.loads(_file(project, project_file).read_text(encoding="utf-8"))
    theirs = json.loads(peer.read(project_file))
    assert mine["documents"], "the template creates documents"
    mine["documents"][0]["last_compile_id"] = _COMPILE_MINE
    mine["updated_at"] = "2030-01-01T10:00:00Z"
    theirs["documents"][0]["last_compile_id"] = _COMPILE_THEIRS
    theirs["updated_at"] = "2030-01-02T10:00:00Z"
    _file(project, project_file).write_text(json.dumps(mine, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "-c", "user.name=T", "-c", "user.email=t@test.local", "commit", "--quiet", "-m", "my compile")
    peer.write(project_file, json.dumps(theirs, ensure_ascii=False, indent=2) + "\n")
    peer.commit_push("their compile")

    operation = await _sync(stack, project)

    assert operation.status == "succeeded", operation.error
    assert operation.result is not None
    assert operation.result.outcome == "merged"
    assert operation.result.conflicts is None
    merged = json.loads(_file(project, project_file).read_text(encoding="utf-8"))
    # Локальное поле остаётся моим, время правки берётся позднее.
    assert merged["documents"][0]["last_compile_id"] == _COMPILE_MINE
    assert merged["updated_at"].startswith("2030-01-02")
    assert remote.head() == _git(project, "rev-parse", "master")


async def test__sync__both_sides_changed_binary__newest_wins_and_loser_kept_beside(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    _file(project, "figures").mkdir(exist_ok=True)
    _file(project, "figures/chart.png").write_bytes(b"\x89PNG\r\n\x00base")
    _git(project, "add", "-A")
    _git(project, "-c", "user.name=T", "-c", "user.email=t@test.local", "commit", "--quiet", "-m", "chart")
    await _sync_ok(stack, project)
    peer.pull()
    _file(project, "figures/chart.png").write_bytes(b"\x89PNG\r\n\x00mine")
    _git(project, "add", "-A")
    _git(project, "-c", "user.name=T", "-c", "user.email=t@test.local", "commit", "--quiet", "-m", "mine")
    peer.write("figures/chart.png", b"\x89PNG\r\n\x00theirs")
    peer.commit_push("theirs")

    result = await _sync_ok(stack, project)

    assert result.outcome == "merged"
    binary = [a for a in result.auto if a.action == "binary_newest"]
    assert len(binary) == 1
    assert binary[0].copy_path is not None
    winner = _file(project, "figures/chart.png").read_bytes()
    loser = _file(project, binary[0].copy_path).read_bytes()
    assert {winner, loser} == {b"\x89PNG\r\n\x00mine", b"\x89PNG\r\n\x00theirs"}


# --- конфликты ----------------------------------------------------------------------------------------------------


async def _make_text_conflict(stack: Stack, project: dict[str, Any], remote: BareRemote) -> tuple[Peer, str, str]:
    peer = await _connect_in_sync(stack, project, remote)
    path = _file(project, TRACKED_FILE)
    lines = path.read_text(encoding="utf-8").splitlines()
    mine = [*lines[:-1], "% conflicting line: mine", ""]
    theirs = [*lines[:-1], "% conflicting line: theirs", ""]
    path.write_text("\n".join(mine), encoding="utf-8")
    _git(project, "add", "-A")
    _git(project, "-c", "user.name=T", "-c", "user.email=t@test.local", "commit", "--quiet", "-m", "mine")
    peer.write(TRACKED_FILE, "\n".join(theirs))
    their_commit = peer.commit_push("theirs")
    return peer, their_commit, path.read_text(encoding="utf-8")


async def test__sync__conflicts__disk_untouched_and_pending_persisted(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    _, theirs, my_text = await _make_text_conflict(stack, project, remote)
    head = _git(project, "rev-parse", "master")
    remote_head = remote.head()

    result = await _sync_ok(stack, project)

    assert result.outcome == "conflicts"
    assert result.conflicts is not None
    assert (result.conflicts.files_total, result.conflicts.files_open) == (1, 1)
    assert result.merge_commit is None
    assert _file(project, TRACKED_FILE).read_text(encoding="utf-8") == my_text
    assert "hse:ours" not in my_text
    assert _git(project, "rev-parse", "master") == head
    assert remote.head() == remote_head
    pending = _state(project)["pending"]
    assert pending["theirs"] == theirs
    assert pending["ours"] == head
    assert pending["base"]
    assert (pending["files_total"], pending["files_open"]) == (1, 1)
    assert pending["session_id"]
    status = await _status(stack, project)
    assert status.ui_state == "conflicts"
    assert status.pending is not None
    assert status.pending.session_id == pending["session_id"]
    assert status.last_sync is not None
    assert status.last_sync.outcome == "conflicts"


async def test__sync__conflicts_again__keeps_session_while_conflict_is_the_same(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _make_text_conflict(stack, project, remote)
    await _sync_ok(stack, project)
    first = _state(project)["pending"]["session_id"]
    _snapshot_unrelated = _file(project, "notes.txt")
    _snapshot_unrelated.write_text("unrelated edit\n", encoding="utf-8")

    result = await _sync_ok(stack, project)

    assert result.outcome == "conflicts"
    assert _state(project)["pending"]["session_id"] == first


async def test__sync__conflict_with_clean_files_alongside__nothing_is_written(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer, _, _ = await _make_text_conflict(stack, project, remote)
    peer.pull()
    peer.write("notes/also-theirs.txt", "clean incoming\n")
    peer.commit_push("another file")

    result = await _sync_ok(stack, project)

    assert result.outcome == "conflicts"
    assert not _file(project, "notes/also-theirs.txt").exists()
    assert [a.path for a in result.auto] == ["notes/also-theirs.txt"]


async def test__sync__theirs_already_contained__stale_pending_is_dropped(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer, _, _ = await _make_text_conflict(stack, project, remote)
    await _sync_ok(stack, project)
    assert _state(project)["pending"] is not None
    # Человек сам привёл ветку к чужой другим путём: сессия потеряла смысл.
    _git(project, "fetch", "--quiet", remote.url, "refs/heads/main:refs/remotes/origin/main")
    _git(project, "reset", "--hard", "--quiet", "refs/remotes/origin/main")

    result = await _sync_ok(stack, project)

    assert result.outcome == "up_to_date"
    assert _state(project)["pending"] is None
    del peer


# --- гонка при отправке ------------------------------------------------------------------------------------------


def _interfere_before_push(monkeypatch: pytest.MonkeyPatch, transport: Any, action: Callable[[int], None]) -> list[int]:
    """Перед каждой отправкой «другая Студия» успевает записать в репозиторий своё."""
    calls: list[int] = []
    original = transport.push

    async def push(*args: Any, **kwargs: Any) -> None:
        calls.append(len(calls) + 1)
        action(len(calls))
        await original(*args, **kwargs)

    monkeypatch.setattr(transport, "push", push)
    return calls


async def test__sync__remote_moved_during_push__retries_with_full_fetch_and_merge(
    stack: Stack, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    _snapshot(project, "local work")
    transport = await stack.get(IGitTransport)

    def interfere(call: int) -> None:
        if call == 1:
            peer.write("notes/race.txt", "pushed in between\n")
            peer.commit_push("race")

    calls = _interfere_before_push(monkeypatch, transport, interfere)

    result = await _sync_ok(stack, project)

    assert calls == [1, 2]
    assert result.outcome == "merged"
    assert result.pulled_commits == 1
    assert remote.head() == _git(project, "rev-parse", "master")
    assert _file(project, "notes/race.txt").exists()


async def test__sync__remote_keeps_moving__fails_with_remote_moved_after_three_rounds(
    stack: Stack, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    _snapshot(project, "local work")
    transport = await stack.get(IGitTransport)

    def interfere(call: int) -> None:
        peer.pull()
        peer.write(f"notes/race-{call}.txt", "again\n")
        peer.commit_push(f"race {call}")

    calls = _interfere_before_push(monkeypatch, transport, interfere)

    operation = await _sync(stack, project)

    assert calls == [1, 2, 3]
    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "remote_moved"
    # Слияния, уже сделанные локально, остаются: следующая синхронизация их не повторяет.
    assert (await _status(stack, project)).health == "ok"


# --- проверки перед отправкой -------------------------------------------------------------------------------------


async def test__sync__large_file__stops_before_upload(
    stack: Stack, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Политика собирается при первом обращении к синхронизации, поэтому порог меняется до подключения.
    monkeypatch.setattr(app_settings.git, "large_file_warn_bytes", 20_000)
    await _connect_in_sync(stack, project, remote)
    before = remote.head()
    transport = await stack.get(IGitTransport)
    pushes: list[object] = []
    original = transport.push

    async def spy(*args: Any, **kwargs: Any) -> None:
        pushes.append(args)
        await original(*args, **kwargs)

    monkeypatch.setattr(transport, "push", spy)
    _file(project, "assets").mkdir(exist_ok=True)
    _file(project, "assets/video.bin").write_bytes(bytes(range(256)) * 200)

    operation = await _sync(stack, project)

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "large_file"
    assert pushes == []
    assert remote.head() == before


async def test__sync__conflict_markers_in_a_file__stop_before_upload(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect_in_sync(stack, project, remote)
    before = remote.head()
    marked = "a\n<<<<<<< hse:ours\nx\n||||||| hse:base\ny\n=======\nz\n>>>>>>> hse:theirs\n"
    _file(project, "notes.txt").write_text(marked, encoding="utf-8")

    operation = await _sync(stack, project)

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "sync_incomplete"
    assert remote.head() == before


# --- безопасность чужого дерева ----------------------------------------------------------------------------------


async def test__sync__symlink_from_remote__is_skipped_with_warning(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    peer.write("notes/real.txt", "fine\n")
    (peer.path / "evil").symlink_to("/etc")
    peer.commit_push("link and file")

    result = await _sync_ok(stack, project)

    assert result.outcome == "merged"
    assert not _file(project, "evil").exists()
    assert not _file(project, "evil").is_symlink()
    assert _file(project, "notes/real.txt").exists()
    assert [(w.code, w.paths) for w in result.warnings] == [("unsafe_path", ["evil"])]


@pytest.mark.parametrize("local_edit", [False, True], ids=["fast_forward", "merge"])
async def test__sync__case_only_rename_on_remote__file_stays_on_disk(
    stack: Stack, project: dict[str, Any], remote: BareRemote, local_edit: bool
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    peer.write("notes/a.txt", "заметка\n")
    peer.commit_push("add note")
    await _sync_ok(stack, project)
    peer.git("mv", "notes/a.txt", "Notes/a.txt")
    peer.commit_push("rename note by case")
    if local_edit:
        _snapshot(project, "local work")

    result = await _sync_ok(stack, project)

    assert result.outcome == ("merged" if local_edit else "fast_forwarded")
    # На файловой системе без учёта регистра имя на диске могло остаться прежним, содержимое обязано уцелеть.
    assert _file(project, "Notes/a.txt").read_text(encoding="utf-8") == "заметка\n"
    assert _git(project, "ls-tree", "-r", "--name-only", "HEAD").splitlines().count("Notes/a.txt") == 1
    assert _git(project, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""


async def test__sync__incoming_file_over_untracked_local_one__local_copy_is_kept_beside(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    # PDF по умолчанию вне истории: у меня он неотслеживаемый, а коллега с track_pdf его закоммитил.
    _file(project, "figures").mkdir(exist_ok=True)
    _file(project, "figures/scheme.pdf").write_bytes(b"%PDF-mine")
    peer.write("figures/scheme.pdf", b"%PDF-theirs")
    peer.commit_push("tracked pdf")

    result = await _sync_ok(stack, project)

    assert result.outcome == "fast_forwarded"
    assert _file(project, "figures/scheme.pdf").read_bytes() == b"%PDF-theirs"
    assert _file(project, "figures/scheme.local.pdf").read_bytes() == b"%PDF-mine"
    assert "scheme.local.pdf" not in _git(project, "ls-files")


async def test__sync__remote_project_is_newer_studio__refused_before_anything_starts(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    data = json.loads(peer.read(".hse-studio/project.json"))
    data["schema"] = {"version": 9, "read_compat": 9, "write_compat": 9, "written_by": "9.0.0"}
    peer.write(".hse-studio/project.json", json.dumps(data))
    peer.commit_push("future studio")
    _git(project, "fetch", "--quiet", remote.url, "refs/heads/main:refs/remotes/origin/main")

    resp = await _start(stack, project)

    assert resp.status_code == 409
    body = _error(resp)
    assert (body.code, body.required_studio) == ("remote_schema_newer", "9.0.0")


@pytest.mark.parametrize(
    "garbage",
    [{"documents": "x"}, {"authors": 5}, {"meta": [1, 2]}],
    ids=["documents", "authors", "meta"],
)
async def test__sync__remote_project_json_the_studio_cannot_load__refused_and_project_stays_open(
    stack: Stack, project: dict[str, Any], remote: BareRemote, garbage: dict[str, Any]
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    before = _file(project, ".hse-studio/project.json").read_bytes()
    peer.write(".hse-studio/project.json", json.dumps({**json.loads(peer.read(".hse-studio/project.json")), **garbage}))
    peer.commit_push("broken project file")

    operation = await _sync(stack, project)

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "not_a_studio_project"
    assert _file(project, ".hse-studio/project.json").read_bytes() == before
    assert (await stack.client.get(f"/api/v1/projects/{project['id']}")).status_code == 200


@pytest.mark.parametrize("local_edit", [False, True], ids=["fast_forward", "merge"])
async def test__sync__incoming_file_over_the_size_limit__refused_before_it_is_read_or_written(
    stack: Stack,
    project: dict[str, Any],
    remote: BareRemote,
    monkeypatch: pytest.MonkeyPatch,
    local_edit: bool,
) -> None:
    # Политика собирается при первом обращении к синхронизации, поэтому предел меняется до подключения.
    monkeypatch.setattr(app_settings.git, "max_incoming_blob_bytes", 100_000)
    peer = await _connect_in_sync(stack, project, remote)
    peer.write("assets/big.bin", bytes(300_000))
    peer.commit_push("a big file")
    if local_edit:
        _snapshot(project, "local work")
    head = _git(project, "rev-parse", "master")

    operation = await _sync(stack, project)

    assert operation.status == "failed"
    assert operation.error is not None
    assert "big.bin" in operation.error.detail
    assert not _file(project, "assets/big.bin").exists()
    assert _git(project, "rev-parse", "master") == head


@pytest.mark.skipif(sys.platform == "win32", reason="на Windows двоеточия в имени файла быть не может")
async def test__sync__colon_in_a_file_name__file_survives_the_merge_and_the_push(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    peer.write("thesis/Отчёт: итог.tex", "итог\n")
    peer.commit_push("report with a colon")
    _snapshot(project, "local work")

    result = await _sync_ok(stack, project)

    assert result.outcome == "merged"
    assert result.warnings == []
    assert _file(project, "thesis/Отчёт: итог.tex").read_text(encoding="utf-8") == "итог\n"
    pushed = run_git("-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", "main", git_dir=remote.path)
    assert "thesis/Отчёт: итог.tex" in pushed.splitlines()


@pytest.mark.parametrize("their_side", ["file", "folder"])
async def test__sync__file_and_folder_with_one_name__refused_clearly_and_nothing_is_left_behind(
    stack: Stack, project: dict[str, Any], remote: BareRemote, their_side: str
) -> None:
    peer = await _connect_in_sync(stack, project, remote)
    mine, theirs = ("notes/x.txt", "notes") if their_side == "file" else ("notes", "notes/x.txt")
    _file(project, mine).parent.mkdir(parents=True, exist_ok=True)
    _file(project, mine).write_text("мой\n", encoding="utf-8")
    peer.write(theirs, "чужой\n")
    peer.commit_push("same name")

    for _ in range(2):
        operation = await _sync(stack, project)

        assert operation.status == "failed"
        assert operation.error is not None
        assert operation.error.code == "git_error"
        assert "notes" in operation.error.detail
        assert not list(Path(project["folder"]).rglob("*.hse-update.tmp"))
    assert _file(project, mine).read_text(encoding="utf-8") == "мой\n"
    assert not any(path.endswith(".hse-update.tmp") for path in _git(project, "ls-files").splitlines())


# --- отказы до начала --------------------------------------------------------------------------------------------


async def test__sync__no_remote__404(stack: Stack, project: dict[str, Any]) -> None:
    resp = await _start(stack, project)

    assert resp.status_code == 404


async def test__sync__unknown_project__404(stack: Stack) -> None:
    resp = await stack.client.post("/api/v1/projects/00000000-0000-0000-0000-000000000000/git/sync", json={})

    assert resp.status_code == 404


async def test__sync__without_profile__profile_required(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect_in_sync(stack, project, remote)
    assert (await stack.client.delete("/api/v1/profile")).status_code == 200

    resp = await _start(stack, project)

    assert resp.status_code == 409
    assert _error(resp).code == "profile_required"


async def test__sync__off_branch__409(stack: Stack, project: dict[str, Any], remote: BareRemote) -> None:
    await _connect_in_sync(stack, project, remote)
    _git(project, "checkout", "--quiet", "-b", "other")

    resp = await _start(stack, project)

    assert resp.status_code == 409
    assert _error(resp).code == "off_branch"


async def test__sync__already_running__sync_busy_with_operation_id(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect_in_sync(stack, project, remote)
    operations = await stack.get(IGitOperationRegistry)
    running = operations.begin(OperationKind.sync, project_id=None, folder=Path(project["folder"]))

    resp = await _start(stack, project)

    assert resp.status_code == 409
    body = _error(resp)
    assert (body.code, body.operation_id) == ("sync_busy", running.id)


async def test__sync__read_only_project__423_and_nothing_changes(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect_in_sync(stack, project, remote)
    path = _file(project, ".hse-studio/project.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema"] = {**data.get("schema", {}), "version": 99, "read_compat": 1, "write_compat": 99}
    path.write_text(json.dumps(data), encoding="utf-8")
    before = _git(project, "rev-parse", "master")

    resp = await _start(stack, project)

    assert resp.status_code == 423
    assert _git(project, "rev-parse", "master") == before


# --- сеть не держит проект ----------------------------------------------------------------------------------------


async def test__sync__slow_fetch__edits_are_not_blocked_and_not_lost(
    stack: Stack, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connect_in_sync(stack, project, remote)
    transport = await stack.get(IGitTransport)
    gate = asyncio.Event()
    entered = asyncio.Event()
    original = transport.fetch

    async def slow_fetch(*args: Any, **kwargs: Any) -> None:
        entered.set()
        await gate.wait()
        await original(*args, **kwargs)

    monkeypatch.setattr(transport, "fetch", slow_fetch)
    started = await _start(stack, project)
    async with asyncio.timeout(10):
        await entered.wait()
    status = await _status(stack, project)
    assert status.ui_state == "syncing"
    assert status.operation is not None
    assert status.operation.phase == "fetch"

    saved = await asyncio.wait_for(
        stack.client.put(
            f"/api/v1/projects/{project['id']}/files/notes/during-network.txt", content=b"written while fetching\n"
        ),
        timeout=5,
    )
    assert saved.status_code in (200, 204), saved.text
    gate.set()
    operation = await _wait(stack, started.json()["operation_id"])

    assert operation.status == "succeeded", operation.error
    assert _file(project, "notes/during-network.txt").read_text(encoding="utf-8") == "written while fetching\n"
    assert "notes/during-network.txt" in _git(project, "ls-tree", "-r", "--name-only", "master").splitlines()
    assert remote.head() == _git(project, "rev-parse", "master")


async def test__sync__cancel_during_fetch__operation_is_cancelled_and_project_untouched(
    stack: Stack, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connect_in_sync(stack, project, remote)
    transport = await stack.get(IGitTransport)
    entered = asyncio.Event()

    async def hanging_fetch(*args: Any, **kwargs: Any) -> None:
        entered.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(transport, "fetch", hanging_fetch)
    started = await _start(stack, project)
    async with asyncio.timeout(10):
        await entered.wait()
    operation_id = started.json()["operation_id"]

    cancelled = await stack.client.post(f"/api/v1/git/operations/{operation_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    operation = await _wait(stack, operation_id)

    assert operation.status == "cancelled"
    assert (await _status(stack, project)).operation is None
    assert not (_store(project).parent / "update" / "journal.json").exists()


async def test__sync__waits_for_running_build__then_gives_up_with_sync_busy_build(
    stack: Stack, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connect_in_sync(stack, project, remote)
    dispatcher = await stack.get(IJobDispatcher)
    monkeypatch.setattr(dispatcher, "has_active_for_folder", lambda folder: True)
    monkeypatch.setattr(sync_project, "BUILD_WAIT_S", 0.3)
    monkeypatch.setattr(sync_project, "BUILD_POLL_S", 0.05)

    operation = await _sync(stack, project)

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "sync_busy_build"
    assert operation.phase == OperationPhase.queued.value


async def test__sync__build_finishes_while_waiting__sync_proceeds(
    stack: Stack, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connect_in_sync(stack, project, remote)
    dispatcher = await stack.get(IJobDispatcher)
    checks = {"n": 0}

    def busy_twice(folder: Path) -> bool:
        checks["n"] += 1
        return checks["n"] <= 2

    monkeypatch.setattr(dispatcher, "has_active_for_folder", busy_twice)
    monkeypatch.setattr(sync_project, "BUILD_POLL_S", 0.02)
    _snapshot(project, "local work")

    result = await _sync_ok(stack, project)

    assert result.outcome == "pushed"
    assert checks["n"] > 2


# --- падение посреди применения -----------------------------------------------------------------------------------


async def _diverge_cleanly(stack: Stack, project: dict[str, Any], remote: BareRemote) -> Peer:
    peer = await _connect_in_sync(stack, project, remote)
    _snapshot(project, "local work")
    peer.write("notes/incoming.txt", "incoming\n")
    peer.commit_push("incoming")
    return peer


async def test__sync__failure_while_committing__rolls_back_files_and_next_sync_succeeds(
    stack: Stack, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _diverge_cleanly(stack, project, remote)
    head = _git(project, "rev-parse", "master")
    from hse_doc_studio.infra.git_sync.merge_committer import GitMergeCommitter

    original = GitMergeCommitter.commit_merge

    def broken(self: Any, *args: Any, **kwargs: Any) -> str:
        raise RuntimeError("disk full")

    monkeypatch.setattr(GitMergeCommitter, "commit_merge", broken)

    operation = await _sync(stack, project)

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "git_error"
    assert _git(project, "rev-parse", "master") == head
    assert not _file(project, "notes/incoming.txt").exists()
    assert not (_store(project).parent / "update" / "journal.json").exists()

    monkeypatch.setattr(GitMergeCommitter, "commit_merge", original)
    result = await _sync_ok(stack, project)
    assert result.outcome == "merged"
    assert _file(project, "notes/incoming.txt").exists()


async def test__sync__process_killed_before_commit__startup_recovery_restores_the_project(
    stack: Stack, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _diverge_cleanly(stack, project, remote)
    head = _git(project, "rev-parse", "master")
    from hse_doc_studio.infra.git_sync.merge_committer import GitMergeCommitter

    def killed(self: Any, *args: Any, **kwargs: Any) -> str:
        raise RuntimeError("killed")

    # Процесс умер: ни откат по исключению, ни очистка журнала не успели выполниться.
    monkeypatch.setattr(GitMergeCommitter, "commit_merge", killed)
    monkeypatch.setattr(TemplateUpdateTransaction, "recover", lambda self, project, journal: False)

    operation = await _sync(stack, project)

    assert operation.status == "failed"
    journal = _store(project).parent / "update" / "journal.json"
    assert journal.exists()
    assert json.loads(journal.read_text(encoding="utf-8"))["kind"] == "sync"
    assert _file(project, "notes/incoming.txt").exists()
    detail = await stack.client.get(f"/api/v1/projects/{project['id']}")
    assert detail.json()["access"]["mode"] == "read_only"
    # Пока журнал не разобран, проект только для чтения: синхронизацию не принимает уже общая защита записи.
    blocked = await _start(stack, project)
    assert blocked.status_code == 423

    monkeypatch.undo()
    recovered = await _recover(stack)

    assert [r.finalized for r in recovered.recovered] == [False]
    assert not journal.exists()
    assert not _file(project, "notes/incoming.txt").exists()
    assert _git(project, "rev-parse", "master") == head
    result = await _sync_ok(stack, project)
    assert result.outcome == "merged"


async def test__sync__process_killed_after_branch_moved__startup_recovery_finalizes(
    stack: Stack, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _diverge_cleanly(stack, project, remote)
    from hse_doc_studio.infra.git_sync.merge_committer import GitMergeCommitter

    original = GitMergeCommitter.advance_branch

    def moved_then_killed(self: Any, *args: Any, **kwargs: Any) -> bool:
        original(self, *args, **kwargs)
        raise RuntimeError("killed after update-ref")

    monkeypatch.setattr(GitMergeCommitter, "advance_branch", moved_then_killed)
    monkeypatch.setattr(TemplateUpdateTransaction, "recover", lambda self, project, journal: False)

    operation = await _sync(stack, project)

    assert operation.status == "failed"
    journal = _store(project).parent / "update" / "journal.json"
    assert journal.exists()
    merged = _git(project, "rev-parse", "master")

    monkeypatch.undo()
    recovered = await _recover(stack)

    assert [r.finalized for r in recovered.recovered] == [True]
    assert not journal.exists()
    assert _git(project, "rev-parse", "master") == merged
    assert _file(project, "notes/incoming.txt").exists()
    result = await _sync_ok(stack, project)
    assert result.outcome == "pushed"
    assert remote.head() == merged


# --- здоровье подключения -----------------------------------------------------------------------------------------


async def test__sync__remote_unreachable__fails_with_offline_and_marks_health(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect_in_sync(stack, project, remote)
    remote.path.rename(remote.path.with_name("gone.git"))

    operation = await _sync(stack, project)

    assert operation.status == "failed"
    assert operation.error is not None
    status = await _status(stack, project)
    assert status.last_error is not None
    assert status.last_error.code == operation.error.code
    assert status.health != "ok"
    assert status.operation is None


async def test__sync__after_failure_succeeds__health_and_error_are_cleared(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect_in_sync(stack, project, remote)
    moved = remote.path.with_name("gone.git")
    remote.path.rename(moved)
    failed = await _sync(stack, project)
    assert failed.status == "failed"
    moved.rename(remote.path)

    result = await _sync_ok(stack, project)

    assert result.outcome == "up_to_date"
    status = await _status(stack, project)
    assert (status.health, status.last_error) == ("ok", None)
