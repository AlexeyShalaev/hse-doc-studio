"""Экран конфликтов через настоящий API: сессия, подробности файлов, черновики, применение и отказ.

Удалённый репозиторий локальный голый (file://), «другая Студия» это обычная рабочая копия. Проект, его
хранилище и git настоящие, сети нет. Ответы проверяются теми же строгими моделями, что и эталоны контракта.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from hse_doc_studio.api.schemas.git_sync import (
    ConflictDiffResponse,
    ConflictFileDetail,
    ConflictSessionResponse,
    GitErrorBody,
    GitStatusResponse,
    OperationResponse,
    TextFileDetail,
)
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.git_remote import BareRemote, make_bare_remote, run_git
from tests.integration.api.vcs.conftest import TRACKED_FILE, create_project

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "git-sync" / "fixtures"
_PROFILE = {"name": "Анна Петрова", "email": "a.petrova@edu.hse.ru"}
_PEER = ("Борис Сидоров", "b.sidorov@edu.hse.ru")
_PROJECT_FILE = ".hse-studio/project.json"
_MINE = "% conflicting line: mine"
_THEIRS = "% conflicting line: theirs"
_DETAIL = TypeAdapter(ConflictFileDetail)


@dataclass
class Stack:
    client: AsyncClient
    tmp_path: Path


@pytest_asyncio.fixture
async def stack(tmp_path: Path) -> AsyncIterator[Stack]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir)
    app = create_test_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put("/api/v1/profile", json=_PROFILE)
        assert resp.status_code == 200, resp.text
        yield Stack(client, tmp_path)
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


def _git(project: dict[str, Any], *args: str) -> str:
    return run_git(*args, git_dir=_store(project), work_tree=Path(project["folder"]))


def _file(project: dict[str, Any], rel: str) -> Path:
    return Path(project["folder"]) / rel


def _state(project: dict[str, Any]) -> dict[str, Any]:
    return json.loads((_store(project) / "hse-sync.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _commit(project: dict[str, Any], message: str) -> str:
    _git(project, "add", "-A")
    _git(project, "-c", "user.name=T", "-c", "user.email=t@test.local", "commit", "--quiet", "-m", message)
    return _git(project, "rev-parse", "HEAD")


def _url(project: dict[str, Any], tail: str) -> str:
    return f"/api/v1/projects/{project['id']}/git/{tail}"


def _error(resp: Any) -> GitErrorBody:
    return GitErrorBody.model_validate(resp.json())


def _edited(text: str, first: str, last: str) -> str:
    """Файл с изменённой первой и последней строкой: два независимых места."""
    lines = text.splitlines()
    return "\n".join([first, *lines[1:-1], last]) + "\n"


async def _connect(stack: Stack, project: dict[str, Any], remote: BareRemote) -> Peer:
    _git(project, "push", "--quiet", remote.url, "master:refs/heads/main")
    resp = await stack.client.put(_url(project, "remote"), json={"url": remote.url, "credential_id": None})
    assert resp.status_code == 200, resp.text
    return Peer(stack.tmp_path / "peer", remote)


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
    started = await stack.client.post(_url(project, "sync"), json={})
    assert started.status_code == 202, started.text
    return await _wait(stack, started.json()["operation_id"])


async def _session(stack: Stack, project: dict[str, Any]) -> ConflictSessionResponse:
    resp = await stack.client.get(_url(project, "conflicts"))
    assert resp.status_code == 200, resp.text
    return ConflictSessionResponse.model_validate(resp.json())


async def _resolve(
    stack: Stack, project: dict[str, Any], session: ConflictSessionResponse, resolutions: Any, *, push: bool = True
) -> Any:
    return await stack.client.post(
        _url(project, "conflicts/resolve"),
        json={"fingerprint": session.fingerprint, "resolutions": resolutions, "push": push},
    )


async def _resolve_ok(
    stack: Stack, project: dict[str, Any], session: ConflictSessionResponse, resolutions: Any, *, push: bool = True
) -> OperationResponse:
    resp = await _resolve(stack, project, session, resolutions, push=push)
    assert resp.status_code == 202, resp.text
    operation = await _wait(stack, resp.json()["operation_id"])
    assert operation.status == "succeeded", operation.error
    return operation


async def _status(stack: Stack, project: dict[str, Any]) -> GitStatusResponse:
    resp = await stack.client.get(f"/api/v1/projects/{project['id']}/git")
    assert resp.status_code == 200, resp.text
    return GitStatusResponse.model_validate(resp.json())


async def _text_conflict(stack: Stack, project: dict[str, Any], remote: BareRemote) -> Peer:
    """Обе стороны правят первую и последнюю строку главного файла по-разному: два участка конфликта."""
    peer = await _connect(stack, project, remote)
    path = _file(project, TRACKED_FILE)
    original = path.read_text(encoding="utf-8")
    path.write_text(_edited(original, f"{_MINE} first", f"{_MINE} last"), encoding="utf-8")
    _commit(project, "mine")
    peer.write(TRACKED_FILE, _edited(original, f"{_THEIRS} first", f"{_THEIRS} last"))
    peer.commit_push("theirs")
    operation = await _sync(stack, project)
    assert operation.status == "succeeded", operation.error
    assert operation.result is not None
    assert operation.result.outcome == "conflicts"
    return peer


def _hunk_keys(detail: TextFileDetail) -> list[str]:
    return [seg.key for seg in detail.segments if seg.type == "hunk"]


async def _detail(stack: Stack, project: dict[str, Any], path: str) -> Any:
    resp = await stack.client.get(_url(project, "conflicts/file"), params={"path": path})
    assert resp.status_code == 200, resp.text
    return _DETAIL.validate_python(resp.json())


# --- сессия ------------------------------------------------------------------------------------------------------


async def test__session__text_conflict__lists_the_file_with_both_hunks(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)

    session = await _session(stack, project)

    assert session.id == _state(project)["pending"]["session_id"]
    assert session.counts.conflict == 1
    assert session.unresolved == 1
    assert session.drafts_saved_at is None
    assert session.ours.commit == _git(project, "rev-parse", "master")
    assert session.ours.author is not None
    assert session.theirs.author is not None
    assert session.theirs.message == "theirs"
    assert session.base is not None
    [item] = [f for f in session.files if f.action == "conflict"]
    assert (item.path, item.kind, item.conflict_type) == (TRACKED_FILE, "text", "content")
    assert (item.hunks, item.open_hunks, item.resolved) == (2, 2, False)
    assert item.allowed == ["mine", "theirs"]
    assert item.sides.theirs.author is not None
    assert item.sides.ours.exists
    assert item.sides.base.exists
    assert item.doc_id is not None


async def test__session__keys_match_the_contract_fixture(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    resp = await stack.client.get(_url(project, "conflicts"))
    body = resp.json()
    fixture = json.loads((_FIXTURES / "ConflictSession" / "mixed.json").read_text(encoding="utf-8"))

    assert body.keys() == fixture.keys()
    assert body["files"][0].keys() == fixture["files"][0].keys()
    assert body["files"][0]["sides"].keys() == fixture["files"][0]["sides"].keys()
    assert body["ours"].keys() == fixture["ours"].keys()


async def test__session__without_pending__is_404_no_conflicts(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect(stack, project, remote)

    resp = await stack.client.get(_url(project, "conflicts"))

    assert resp.status_code == 404
    assert _error(resp).code == "no_conflicts"


async def test__session__clean_files_alongside__are_listed_as_auto(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _text_conflict(stack, project, remote)
    peer.pull()
    peer.write("notes/also-theirs.txt", "clean incoming\n")
    peer.commit_push("another file")
    await _sync(stack, project)

    session = await _session(stack, project)

    auto = [f for f in session.files if f.action != "conflict"]
    assert [(f.path, f.action, f.resolved) for f in auto] == [("notes/also-theirs.txt", "take_theirs", True)]
    assert session.counts.model_dump() == {"conflict": 1, "auto": 1, "total": 2}
    assert [f.action for f in session.files][0] == "conflict"


# --- подробности файла -------------------------------------------------------------------------------------------


async def test__file_detail__text__segments_carry_hunks_with_all_three_sides(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)

    detail = await _detail(stack, project, TRACKED_FILE)

    assert isinstance(detail, TextFileDetail)
    assert detail.eol == "lf"
    assert detail.truncated is False
    hunks = [seg for seg in detail.segments if seg.type == "hunk"]
    assert len(hunks) == 2
    assert hunks[0].ours == [f"{_MINE} first"]
    assert hunks[0].theirs == [f"{_THEIRS} first"]
    assert hunks[0].base[0].startswith("% !TeX")
    assert hunks[0].ours_start == hunks[0].result_start == 1
    assert hunks[1].result_start == hunks[1].ours_start
    assert all(h.key.startswith("h:") for h in hunks)


async def test__file_detail__result_start_follows_the_draft(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    first = _hunk_keys(await _detail(stack, project, TRACKED_FILE))[0]
    draft = {TRACKED_FILE: {"kind": "hunks", "hunks": {first: {"choice": "both"}}}}
    assert (await stack.client.put(_url(project, "conflicts/draft"), json={"resolutions": draft})).status_code == 204

    detail = await _detail(stack, project, TRACKED_FILE)

    hunks = [seg for seg in detail.segments if seg.type == "hunk"]
    assert hunks[1].result_start == hunks[1].ours_start + 1


async def test__file_detail__unknown_path__is_404(stack: Stack, project: dict[str, Any], remote: BareRemote) -> None:
    await _text_conflict(stack, project, remote)

    resp = await stack.client.get(_url(project, "conflicts/file"), params={"path": "nope.tex"})

    assert resp.status_code == 404


async def test__diff__views_show_each_side_and_the_draft_result(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    keys = _hunk_keys(await _detail(stack, project, TRACKED_FILE))
    draft = {TRACKED_FILE: {"kind": "hunks", "hunks": {keys[0]: {"choice": "theirs"}}}}
    await stack.client.put(_url(project, "conflicts/draft"), json={"resolutions": draft})

    async def diff(view: str) -> ConflictDiffResponse:
        resp = await stack.client.get(_url(project, "conflicts/diff"), params={"path": TRACKED_FILE, "view": view})
        assert resp.status_code == 200, resp.text
        return ConflictDiffResponse.model_validate(resp.json())

    ours, theirs, result = await diff("ours"), await diff("theirs"), await diff("result")

    assert f"+{_MINE} first" in ours.patch
    assert f"+{_THEIRS} first" not in ours.patch
    assert f"+{_THEIRS} first" in theirs.patch
    # Результат: первый участок взят у них, второй пока мой.
    assert f"+{_THEIRS} first" in result.patch
    assert f"-{_MINE} first" in result.patch
    assert f"{_MINE} last" not in result.patch
    assert not any(d.binary for d in (ours, theirs, result))


async def test__blob__serves_each_side_without_caching(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)

    async def blob(side: str) -> Any:
        return await stack.client.get(_url(project, "conflicts/blob"), params={"path": TRACKED_FILE, "side": side})

    ours, theirs, base = await blob("ours"), await blob("theirs"), await blob("base")

    assert ours.status_code == theirs.status_code == base.status_code == 200
    assert _MINE.encode() in ours.content
    assert _THEIRS.encode() in theirs.content
    assert _MINE.encode() not in base.content
    assert ours.headers["cache-control"] == "no-store"
    assert ours.headers["x-content-type-options"] == "nosniff"
    assert ours.headers["content-type"] == "application/octet-stream"


async def test__blob__path_outside_the_merge__is_404(stack: Stack, project: dict[str, Any], remote: BareRemote) -> None:
    await _text_conflict(stack, project, remote)

    resp = await stack.client.get(
        _url(project, "conflicts/blob"), params={"path": ".hse-studio/git/config", "side": "ours"}
    )

    assert resp.status_code == 404


# --- черновики ---------------------------------------------------------------------------------------------------


async def test__draft__saved_choices_show_in_the_session_and_survive_a_reload(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    keys = _hunk_keys(await _detail(stack, project, TRACKED_FILE))
    draft = {TRACKED_FILE: {"kind": "hunks", "hunks": {keys[0]: {"choice": "mine"}}}}

    resp = await stack.client.put(_url(project, "conflicts/draft"), json={"resolutions": draft})

    assert resp.status_code == 204
    session = await _session(stack, project)
    [item] = session.files
    assert (item.open_hunks, item.resolved, session.unresolved) == (1, False, 1)
    assert item.resolution is not None
    assert item.resolution.model_dump()["hunks"].keys() == {keys[0]}
    assert session.drafts_saved_at is not None
    assert _state(project)["pending"]["drafts"][TRACKED_FILE]["kind"] == "hunks"

    draft[TRACKED_FILE]["hunks"][keys[1]] = {"choice": "theirs"}  # type: ignore[index]
    await stack.client.put(_url(project, "conflicts/draft"), json={"resolutions": draft})

    session = await _session(stack, project)
    assert (session.files[0].open_hunks, session.files[0].resolved, session.unresolved) == (0, True, 0)
    status = await _status(stack, project)
    assert status.pending is not None
    assert status.pending.files_open == 0


async def test__draft__empty_resolution__clears_the_path(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    choice = {TRACKED_FILE: {"kind": "file", "choice": "theirs"}}
    await stack.client.put(_url(project, "conflicts/draft"), json={"resolutions": choice})
    assert (await _session(stack, project)).files[0].resolved is True

    await stack.client.put(
        _url(project, "conflicts/draft"), json={"resolutions": {TRACKED_FILE: {"kind": "hunks", "hunks": {}}}}
    )

    assert (await _session(stack, project)).files[0].resolved is False
    assert _state(project)["pending"]["drafts"] == {}


@pytest.mark.parametrize(
    "draft",
    [
        {TRACKED_FILE: {"kind": "hunks", "hunks": {"h:00000000": {"choice": "mine"}}}},
        {TRACKED_FILE: {"kind": "hunks", "hunks": {"h:x": {"choice": "sideways"}}}},
        {TRACKED_FILE: {"kind": "file", "choice": "newest"}},
        {TRACKED_FILE: {"kind": "fields", "fields": {"/name": {"choice": "mine"}}}},
        {"not/in/the/merge.tex": {"kind": "file", "choice": "mine"}},
    ],
)
async def test__draft__choice_the_plan_does_not_know__is_422_invalid_resolution(
    stack: Stack, project: dict[str, Any], remote: BareRemote, draft: dict[str, Any]
) -> None:
    await _text_conflict(stack, project, remote)

    resp = await stack.client.put(_url(project, "conflicts/draft"), json={"resolutions": draft})

    assert resp.status_code == 422
    assert _error(resp).code == "invalid_resolution"


async def test__draft__custom_choice_without_text__is_invalid(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    key = _hunk_keys(await _detail(stack, project, TRACKED_FILE))[0]

    resp = await stack.client.put(
        _url(project, "conflicts/draft"),
        json={"resolutions": {TRACKED_FILE: {"kind": "hunks", "hunks": {key: {"choice": "custom"}}}}},
    )

    assert resp.status_code == 422
    assert _error(resp).code == "invalid_resolution"


async def test__draft__without_session__is_404(stack: Stack, project: dict[str, Any], remote: BareRemote) -> None:
    await _connect(stack, project, remote)

    resp = await stack.client.put(_url(project, "conflicts/draft"), json={"resolutions": {}})

    assert resp.status_code == 404


async def test__draft__carries_over_when_a_new_commit_arrives_and_sync_stops_again(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _text_conflict(stack, project, remote)
    keys = _hunk_keys(await _detail(stack, project, TRACKED_FILE))
    draft = {TRACKED_FILE: {"kind": "hunks", "hunks": {keys[0]: {"choice": "both"}, keys[1]: {"choice": "theirs"}}}}
    await stack.client.put(_url(project, "conflicts/draft"), json={"resolutions": draft})
    before = await _session(stack, project)
    peer.pull()
    peer.write("notes/more.txt", "one more file\n")
    peer.commit_push("one more file")

    operation = await _sync(stack, project)

    assert operation.result is not None
    assert operation.result.outcome == "conflicts"
    after = await _session(stack, project)
    assert after.fingerprint != before.fingerprint
    assert after.files[0].resolved is True
    assert after.unresolved == 0
    assert _state(project)["pending"]["drafts"][TRACKED_FILE]["hunks"].keys() == {keys[0], keys[1]}


# --- применение --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "last", "expect_first", "expect_last"),
    [
        ({"choice": "mine"}, {"choice": "mine"}, [f"{_MINE} first"], [f"{_MINE} last"]),
        ({"choice": "theirs"}, {"choice": "theirs"}, [f"{_THEIRS} first"], [f"{_THEIRS} last"]),
        (
            {"choice": "both"},
            {"choice": "both_reverse"},
            [f"{_MINE} first", f"{_THEIRS} first"],
            [f"{_THEIRS} last", f"{_MINE} last"],
        ),
        (
            {"choice": "custom", "text": "% typed by hand"},
            {"choice": "mine"},
            ["% typed by hand"],
            [f"{_MINE} last"],
        ),
    ],
)
async def test__resolve__hunk_choices__are_written_pushed_and_seen_by_the_teammate(
    stack: Stack,
    project: dict[str, Any],
    remote: BareRemote,
    first: dict[str, Any],
    last: dict[str, Any],
    expect_first: list[str],
    expect_last: list[str],
) -> None:
    peer = await _text_conflict(stack, project, remote)
    session = await _session(stack, project)
    keys = _hunk_keys(await _detail(stack, project, TRACKED_FILE))
    resolutions = {TRACKED_FILE: {"kind": "hunks", "hunks": {keys[0]: first, keys[1]: last}}}

    operation = await _resolve_ok(stack, project, session, resolutions)

    assert operation.kind == "resolve"
    assert operation.result is not None
    assert operation.result.outcome == "merged"
    assert operation.result.pushed_commits >= 1
    merged = _file(project, TRACKED_FILE).read_text(encoding="utf-8").splitlines()
    assert merged[: len(expect_first)] == expect_first
    assert merged[-len(expect_last) :] == expect_last
    assert "hse:ours" not in "\n".join(merged)
    head = _git(project, "rev-parse", "master")
    assert remote.head() == head == operation.result.merge_commit
    assert _git(project, "rev-list", "--parents", "-n1", head).count(" ") == 2
    body = _git(project, "log", "-1", "--format=%B", head)
    assert "Hse-Kind: sync" in body
    assert "Hse-Sync: " in body
    assert _state(project)["pending"] is None
    peer.pull()
    assert peer.read(TRACKED_FILE).splitlines()[: len(expect_first)] == expect_first
    status = await _status(stack, project)
    assert status.ui_state == "up_to_date"
    assert _git(project, "status", "--porcelain", "--", ".", ":(exclude)*.pdf") == ""


async def test__resolve__without_resolutions__uses_the_saved_drafts(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    keys = _hunk_keys(await _detail(stack, project, TRACKED_FILE))
    draft = {TRACKED_FILE: {"kind": "hunks", "hunks": {keys[0]: {"choice": "theirs"}, keys[1]: {"choice": "mine"}}}}
    await stack.client.put(_url(project, "conflicts/draft"), json={"resolutions": draft})
    session = await _session(stack, project)

    await _resolve_ok(stack, project, session, None)

    merged = _file(project, TRACKED_FILE).read_text(encoding="utf-8").splitlines()
    assert merged[0] == f"{_THEIRS} first"
    assert merged[-1] == f"{_MINE} last"


async def test__resolve__push_off__merges_locally_and_leaves_the_upload(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    session = await _session(stack, project)
    before = remote.head()

    operation = await _resolve_ok(
        stack, project, session, {TRACKED_FILE: {"kind": "file", "choice": "theirs"}}, push=False
    )

    assert operation.result is not None
    assert (operation.result.outcome, operation.result.pushed_commits) == ("merged", 0)
    assert remote.head() == before
    status = await _status(stack, project)
    assert (status.ui_state, status.relation) == ("ahead", "ahead")
    assert _file(project, TRACKED_FILE).read_text(encoding="utf-8").startswith(f"{_THEIRS} first")


async def test__resolve__whole_text_typed_by_hand__replaces_the_file(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    session = await _session(stack, project)

    await _resolve_ok(stack, project, session, {TRACKED_FILE: {"kind": "text", "content": "\\relax\n"}})

    assert _file(project, TRACKED_FILE).read_text(encoding="utf-8") == "\\relax\n"


async def test__resolve__text_with_hse_markers__is_rejected_and_nothing_changes(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    session = await _session(stack, project)
    head = _git(project, "rev-parse", "master")
    marked = "<<<<<<< hse:ours\nmine\n=======\ntheirs\n>>>>>>> hse:theirs\n"

    resp = await _resolve(stack, project, session, {TRACKED_FILE: {"kind": "text", "content": marked}})

    assert resp.status_code == 422
    assert _error(resp).code == "unresolved_markers"
    assert _git(project, "rev-parse", "master") == head
    assert _state(project)["pending"] is not None


async def test__resolve__hunk_text_with_hse_markers__is_rejected(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    session = await _session(stack, project)
    keys = _hunk_keys(await _detail(stack, project, TRACKED_FILE))
    hunks = {keys[0]: {"choice": "custom", "text": ">>>>>>> hse:theirs"}, keys[1]: {"choice": "mine"}}

    resp = await _resolve(stack, project, session, {TRACKED_FILE: {"kind": "hunks", "hunks": hunks}})

    assert resp.status_code == 422
    assert _error(resp).code == "unresolved_markers"


async def test__resolve__a_conflict_left_undecided__is_422_with_the_paths(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    session = await _session(stack, project)
    keys = _hunk_keys(await _detail(stack, project, TRACKED_FILE))

    partial = await _resolve(
        stack, project, session, {TRACKED_FILE: {"kind": "hunks", "hunks": {keys[0]: {"choice": "mine"}}}}
    )
    nothing = await _resolve(stack, project, session, {})

    for resp in (partial, nothing):
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "unresolved_conflicts"
        assert body["paths"] == [TRACKED_FILE]
    assert _state(project)["pending"] is not None


async def test__resolve__choice_the_file_does_not_allow__is_422_invalid_resolution(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    session = await _session(stack, project)

    resp = await _resolve(stack, project, session, {TRACKED_FILE: {"kind": "file", "choice": "newest"}})

    assert resp.status_code == 422
    assert _error(resp).code == "invalid_resolution"


async def test__resolve__without_session__is_404(stack: Stack, project: dict[str, Any], remote: BareRemote) -> None:
    await _connect(stack, project, remote)

    resp = await stack.client.post(
        _url(project, "conflicts/resolve"), json={"fingerprint": "x", "resolutions": {}, "push": True}
    )

    assert resp.status_code == 404
    assert _error(resp).code == "no_conflicts"


# --- устаревший план ---------------------------------------------------------------------------------------------


def _fetch_tracking(project: dict[str, Any], remote: BareRemote) -> None:
    _git(project, "fetch", "--quiet", remote.url, "refs/heads/main:refs/remotes/origin/main")


async def test__resolve__new_commit_on_their_side__is_409_plan_outdated_and_the_session_follows(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _text_conflict(stack, project, remote)
    old = await _session(stack, project)
    peer.pull()
    peer.write("notes/later.txt", "later\n")
    peer.commit_push("later")
    _fetch_tracking(project, remote)

    resp = await _resolve(stack, project, old, {TRACKED_FILE: {"kind": "file", "choice": "mine"}})

    assert resp.status_code == 409
    assert _error(resp).code == "plan_outdated"
    fresh = await _session(stack, project)
    assert fresh.fingerprint != old.fingerprint
    assert fresh.theirs.commit == _git(project, "rev-parse", "refs/remotes/origin/main")
    again = await _resolve(stack, project, fresh, {TRACKED_FILE: {"kind": "file", "choice": "mine"}})
    assert again.status_code == 202, again.text
    assert (await _wait(stack, again.json()["operation_id"])).status == "succeeded"


async def test__resolve__edit_of_the_conflicted_file_itself__is_409_plan_outdated(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    old = await _session(stack, project)
    path = _file(project, TRACKED_FILE)
    path.write_text(path.read_text(encoding="utf-8") + "% typed after the conflict\n", encoding="utf-8")

    resp = await _resolve(stack, project, old, {TRACKED_FILE: {"kind": "file", "choice": "mine"}})

    assert resp.status_code == 409
    assert _error(resp).code == "plan_outdated"
    # Правка сохранена снимком: следующий запрос видит уже новый план.
    fresh = await _session(stack, project)
    assert fresh.fingerprint != old.fingerprint


async def test__resolve__unrelated_edit_and_compile__do_not_invalidate_the_session(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _text_conflict(stack, project, remote)
    session = await _session(stack, project)
    _file(project, "notes-unrelated.txt").write_text("unrelated edit\n", encoding="utf-8")
    state = json.loads(_file(project, _PROJECT_FILE).read_text(encoding="utf-8"))
    state["documents"][0]["last_compile_id"] = "11111111-1111-4111-8111-111111111111"
    _file(project, _PROJECT_FILE).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _commit(project, "compile")
    _file(project, "notes-unsaved.txt").write_text("not even saved\n", encoding="utf-8")

    assert (await _session(stack, project)).fingerprint == session.fingerprint
    await _resolve_ok(stack, project, session, {TRACKED_FILE: {"kind": "file", "choice": "theirs"}})

    assert _file(project, "notes-unrelated.txt").read_text(encoding="utf-8") == "unrelated edit\n"
    peer.pull()
    assert peer.read("notes-unrelated.txt") == "unrelated edit\n"
    merged = json.loads(_file(project, _PROJECT_FILE).read_text(encoding="utf-8"))
    assert merged["documents"][0]["last_compile_id"] == "11111111-1111-4111-8111-111111111111"


# --- отказ -------------------------------------------------------------------------------------------------------


async def test__abort__clears_the_session_and_leaves_the_tree_alone(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    keys = _hunk_keys(await _detail(stack, project, TRACKED_FILE))
    await stack.client.put(
        _url(project, "conflicts/draft"),
        json={"resolutions": {TRACKED_FILE: {"kind": "hunks", "hunks": {keys[0]: {"choice": "mine"}}}}},
    )
    head = _git(project, "rev-parse", "master")
    text = _file(project, TRACKED_FILE).read_text(encoding="utf-8")
    remote_head = remote.head()

    resp = await stack.client.delete(_url(project, "conflicts"))

    assert resp.status_code == 200, resp.text
    status = GitStatusResponse.model_validate(resp.json())
    assert status.pending is None
    assert status.ui_state == "diverged"
    assert _state(project)["pending"] is None
    assert _git(project, "rev-parse", "master") == head
    assert remote.head() == remote_head
    assert _file(project, TRACKED_FILE).read_text(encoding="utf-8") == text
    assert (await stack.client.get(_url(project, "conflicts"))).status_code == 404
    again = await stack.client.delete(_url(project, "conflicts"))
    assert again.status_code == 200


async def test__abort__then_sync__builds_a_fresh_session(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _text_conflict(stack, project, remote)
    first = await _session(stack, project)
    await stack.client.delete(_url(project, "conflicts"))

    operation = await _sync(stack, project)

    assert operation.result is not None
    assert operation.result.outcome == "conflicts"
    second = await _session(stack, project)
    assert second.id != first.id
    assert second.fingerprint == first.fingerprint


# --- поля, бинарные файлы, удаления ------------------------------------------------------------------------------


async def _rename_both(stack: Stack, project: dict[str, Any], remote: BareRemote) -> Peer:
    peer = await _connect(stack, project, remote)
    mine = json.loads(_file(project, _PROJECT_FILE).read_text(encoding="utf-8"))
    theirs = json.loads(peer.read(_PROJECT_FILE))
    mine["name"], theirs["name"] = "Название: у меня", "Название: у них"
    _file(project, _PROJECT_FILE).write_text(json.dumps(mine, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _commit(project, "rename mine")
    peer.write(_PROJECT_FILE, json.dumps(theirs, ensure_ascii=False, indent=2) + "\n")
    peer.commit_push("rename theirs")
    operation = await _sync(stack, project)
    assert operation.result is not None
    assert operation.result.outcome == "conflicts"
    return peer


async def test__fields__state_file_conflict__lists_the_fields_and_applies_a_choice(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _rename_both(stack, project, remote)
    session = await _session(stack, project)
    [item] = [f for f in session.files if f.path == _PROJECT_FILE]
    assert (item.kind, item.conflict_type, item.fields, item.open_fields) == ("json", "fields", 1, 1)

    detail = await _detail(stack, project, _PROJECT_FILE)
    [field] = [f for f in detail.fields if f.status == "conflict"]
    assert (field.pointer, field.type, field.ours, field.theirs) == (
        "/name",
        "scalar",
        "Название: у меня",
        "Название: у них",
    )
    assert field.allowed == ["mine", "theirs"]

    draft = {_PROJECT_FILE: {"kind": "fields", "fields": {"/name": {"choice": "theirs"}}}}
    await stack.client.put(_url(project, "conflicts/draft"), json={"resolutions": draft})
    assert (await _session(stack, project)).unresolved == 0
    preview = await stack.client.get(_url(project, "conflicts/diff"), params={"path": _PROJECT_FILE, "view": "result"})
    assert '+  "name": "Название: у них"' in preview.json()["patch"]

    await _resolve_ok(stack, project, session, None)

    merged = json.loads(_file(project, _PROJECT_FILE).read_text(encoding="utf-8"))
    assert merged["name"] == "Название: у них"
    peer.pull()
    assert json.loads(peer.read(_PROJECT_FILE))["name"] == "Название: у них"


async def test__fields__a_choice_the_field_does_not_allow__is_422(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _rename_both(stack, project, remote)
    session = await _session(stack, project)

    resp = await _resolve(
        stack, project, session, {_PROJECT_FILE: {"kind": "fields", "fields": {"/name": {"choice": "union"}}}}
    )

    assert resp.status_code == 422
    assert _error(resp).code == "invalid_resolution"


async def _binary_and_delete_conflicts(stack: Stack, project: dict[str, Any], remote: BareRemote) -> Peer:
    peer = await _connect(stack, project, remote)
    _file(project, "figures").mkdir(exist_ok=True)
    _file(project, "figures/chart.png").write_bytes(b"\x89PNG\r\n\x00base")
    _file(project, "notes").mkdir(exist_ok=True)
    _file(project, "notes/draft.tex").write_text("base draft\n", encoding="utf-8")
    _commit(project, "chart and draft")
    assert (await _sync(stack, project)).status == "succeeded"
    peer.pull()
    _file(project, "figures/chart.png").write_bytes(b"\x89PNG\r\n\x00mine")
    _file(project, "notes/draft.tex").write_text("base draft\nmy line\n", encoding="utf-8")
    _commit(project, "mine")
    peer.write("figures/chart.png", b"\x89PNG\r\n\x00theirs")
    (peer.path / "notes/draft.tex").unlink()
    peer.commit_push("theirs")
    operation = await _sync(stack, project)
    assert operation.result is not None
    assert operation.result.outcome == "conflicts"
    return peer


async def test__binary_and_delete__details_and_explicit_choices(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _binary_and_delete_conflicts(stack, project, remote)
    session = await _session(stack, project)
    by_path = {f.path: f for f in session.files}

    chart = by_path["figures/chart.png"]
    assert (chart.action, chart.kind, chart.resolved) == ("binary_newest", "binary", True)
    assert chart.allowed == ["mine", "theirs", "newest"]
    assert chart.default_resolution == "newest"
    assert chart.copy_path is not None
    assert chart.copy_path.startswith("figures/chart.conflict-")
    assert session.counts.conflict == 1
    assert session.counts.auto == 1
    draft = by_path["notes/draft.tex"]
    assert (draft.conflict_type, draft.allowed, draft.sides.theirs.exists) == (
        "deleted_by_them",
        ["mine", "theirs"],
        False,
    )

    chart_detail = await _detail(stack, project, "figures/chart.png")
    assert chart_detail.kind == "binary"
    assert chart_detail.newer in ("ours", "theirs")
    assert chart_detail.copy_path == chart.copy_path
    assert (chart_detail.ours.size, chart_detail.theirs.size) == (
        len(b"\x89PNG\r\n\x00mine"),
        len(b"\x89PNG\r\n\x00theirs"),
    )
    gone = await _detail(stack, project, "notes/draft.tex")
    assert (gone.kind, gone.deleted_by) == ("delete", "theirs")
    png = await stack.client.get(
        _url(project, "conflicts/blob"), params={"path": "figures/chart.png", "side": "theirs"}
    )
    assert png.content == b"\x89PNG\r\n\x00theirs"
    assert png.headers["content-type"] == "image/png"
    assert (
        await stack.client.get(_url(project, "conflicts/diff"), params={"path": "figures/chart.png", "view": "ours"})
    ).json()["binary"] is True

    resolutions = {
        "figures/chart.png": {"kind": "file", "choice": "theirs"},
        "notes/draft.tex": {"kind": "file", "choice": "theirs"},
    }
    await _resolve_ok(stack, project, session, resolutions)

    assert _file(project, "figures/chart.png").read_bytes() == b"\x89PNG\r\n\x00theirs"
    assert not list(_file(project, "figures").glob("chart.conflict-*"))
    assert not _file(project, "notes/draft.tex").exists()
    peer.pull()
    assert not (peer.path / "notes/draft.tex").exists()


async def test__binary__newest_by_default_keeps_the_loser_beside(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    await _binary_and_delete_conflicts(stack, project, remote)
    session = await _session(stack, project)
    chart = next(f for f in session.files if f.path == "figures/chart.png")

    await _resolve_ok(stack, project, session, {"notes/draft.tex": {"kind": "file", "choice": "mine"}})

    assert chart.copy_path is not None
    winner = _file(project, "figures/chart.png").read_bytes()
    loser = _file(project, chart.copy_path).read_bytes()
    assert {winner, loser} == {b"\x89PNG\r\n\x00mine", b"\x89PNG\r\n\x00theirs"}
    assert _file(project, "notes/draft.tex").read_text(encoding="utf-8") == "base draft\nmy line\n"


# --- группа подписей ---------------------------------------------------------------------------------------------


def _signatures(pdf_sha: str, pdf_path: str, extra: str) -> str:
    frozen = {
        "main": {
            "path": pdf_path,
            "sha256": pdf_sha,
            "source_sha256": "s" + extra,
            "size": 8,
            "frozen_at": "2026-10-26T10:00:00Z",
            "stamps_digest": "",
        }
    }
    return json.dumps({"slots": {}, "placements": {}, "frozen": frozen, "detached": {}}, indent=2) + "\n"


async def test__signature_group__follows_one_side_as_a_whole(
    stack: Stack, project: dict[str, Any], remote: BareRemote
) -> None:
    peer = await _connect(stack, project, remote)
    pdf = ".hse-studio/frozen/main.pdf"
    sig = ".hse-studio/signatures.json"
    _file(project, ".hse-studio/frozen").mkdir(parents=True, exist_ok=True)
    _file(project, pdf).write_bytes(b"%PDF-1.4 base")
    _file(project, sig).write_text(_signatures("0" * 64, pdf, "0"), encoding="utf-8")
    _git(project, "add", "-f", "--", pdf, sig)
    _commit(project, "frozen base")
    assert (await _sync(stack, project)).status == "succeeded"
    peer.pull()
    _file(project, pdf).write_bytes(b"%PDF-1.4 mine!")
    _file(project, sig).write_text(_signatures("1" * 64, pdf, "1"), encoding="utf-8")
    _git(project, "add", "-f", "--", pdf, sig)
    _commit(project, "frozen mine")
    peer.write(pdf, b"%PDF-1.4 theirs")
    peer.write(sig, _signatures("2" * 64, pdf, "2"))
    peer.git("add", "-f", "--", pdf, sig)
    peer.commit_push("frozen theirs")
    operation = await _sync(stack, project)
    assert operation.result is not None
    assert operation.result.outcome == "conflicts"

    session = await _session(stack, project)

    [item] = [f for f in session.files if f.path == sig]
    assert item.conflict_type == "signature_group"
    # Замороженный PDF решается вместе с подписями, отдельной строкой его нет.
    assert pdf not in {f.path for f in session.files}
    detail = await _detail(stack, project, sig)
    [group] = [f for f in detail.fields if f.status == "conflict"]
    assert group.pointer == "/signature_groups/main"
    await _resolve_ok(
        stack, project, session, {sig: {"kind": "fields", "fields": {group.pointer: {"choice": "theirs"}}}}
    )

    assert _file(project, pdf).read_bytes() == b"%PDF-1.4 theirs"
    assert json.loads(_file(project, sig).read_text(encoding="utf-8"))["frozen"]["main"]["sha256"] == "2" * 64
    assert not list(_file(project, ".hse-studio/frozen").glob("*.conflict-*"))
