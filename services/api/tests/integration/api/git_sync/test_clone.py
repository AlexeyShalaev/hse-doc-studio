"""Клонирование проекта из удалённого репозитория через настоящий API.

Источником служит проект, созданный в первой Студии (свой data_dir) и отправленный в локальный голый
репозиторий; клонирует вторая Студия со своим data_dir, как это сделал бы коллега. Сеть не нужна, git настоящий.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from hse_doc_studio.api.schemas.git_sync import GitErrorBody, GitStatusResponse, OperationResponse
from hse_doc_studio.infra.git_sync.git_transport import GitTransport
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.git_remote import BareRemote, make_bare_remote, run_git, seed_remote
from tests.integration.api.vcs.conftest import TRACKED_FILE, create_project

_PROFILE = {"name": "Анна Петрова", "email": "a.petrova@edu.hse.ru"}
_POLL_S = 0.02
_WAIT_S = 60.0


@dataclass
class Studio:
    client: AsyncClient
    container: Any
    root: Path


async def _open_studio(root: Path, *, profile: bool = True) -> tuple[Studio, Callable[[], Any]]:
    data_dir = root / "data"
    data_dir.mkdir(parents=True)
    container = create_test_container(data_dir)
    client = AsyncClient(transport=ASGITransport(app=create_test_app(container)), base_url="http://test")
    if profile:
        resp = await client.put("/api/v1/profile", json=_PROFILE)
        assert resp.status_code == 200, resp.text

    async def close() -> None:
        await client.aclose()
        await container.close()

    return Studio(client, container, root), close


@pytest_asyncio.fixture
async def source(tmp_path: Path) -> AsyncIterator[Studio]:
    studio, close = await _open_studio(tmp_path / "source")
    yield studio
    await close()


@pytest_asyncio.fixture
async def target(tmp_path: Path) -> AsyncIterator[Studio]:
    studio, close = await _open_studio(tmp_path / "target")
    yield studio
    await close()


@pytest.fixture
def remote(tmp_path: Path) -> BareRemote:
    return make_bare_remote(tmp_path / "remotes" / "origin.git")


@pytest_asyncio.fixture
async def published(source: Studio, remote: BareRemote) -> dict[str, Any]:
    """Проект первой Студии, чья история лежит в удалённом репозитории."""
    project = await create_project(source.client, source.root / "work" / "thesis")
    _git(project, "push", "--quiet", remote.url, "master:refs/heads/main")
    return project


def _store(project: dict[str, Any]) -> Path:
    return Path(project["folder"]) / ".hse-studio" / "git"


def _git(project: dict[str, Any], *args: str) -> str:
    return run_git(*args, git_dir=_store(project), work_tree=Path(project["folder"]))


def _commit(project: dict[str, Any], remote: BareRemote, message: str, *, force: bool = False) -> None:
    _git(project, "add", "-A", *(["-f"] if force else []), ".")
    _git(project, "-c", "user.name=Test", "-c", "user.email=t@test.local", "commit", "--quiet", "-m", message)
    _git(project, "push", "--quiet", remote.url, "master:refs/heads/main")


def _edit_project_json(project: dict[str, Any], change: Callable[[dict[str, Any]], None]) -> None:
    path = Path(project["folder"]) / ".hse-studio" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def _start(studio: Studio, remote: BareRemote, folder: Path, **body: Any) -> Any:
    return await studio.client.post("/api/v1/git/clone", json={"url": remote.url, "folder": str(folder), **body})


async def _finished(studio: Studio, operation_id: str) -> OperationResponse:
    async with asyncio.timeout(_WAIT_S):
        while True:
            resp = await studio.client.get(f"/api/v1/git/operations/{operation_id}")
            assert resp.status_code == 200, resp.text
            operation = OperationResponse.model_validate(resp.json())
            if operation.status != "running":
                return operation
            await asyncio.sleep(_POLL_S)


async def _clone(studio: Studio, remote: BareRemote, folder: Path, **body: Any) -> OperationResponse:
    resp = await _start(studio, remote, folder, **body)
    assert resp.status_code == 202, resp.text
    return await _finished(studio, resp.json()["operation_id"])


def _error(resp: Any) -> GitErrorBody:
    return GitErrorBody.model_validate(resp.json())


# --- успешное клонирование ------------------------------------------------------------------------


async def test__clone__studio_project__opens_with_full_access(
    target: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    folder = tmp_path / "clones" / "thesis"

    operation = await _clone(target, remote, folder)

    assert operation.status == "succeeded", operation
    assert operation.kind == "clone"
    assert operation.phase == "register"
    result = operation.result
    assert result is not None
    assert (result.project_id, result.folder, result.access) == (
        UUID(published["id"]),
        str(folder),
        "full",
    )
    assert (result.required_studio, result.warnings) == (None, [])
    assert operation.project_id == result.project_id
    shown = await target.client.get(f"/api/v1/projects/{published['id']}")
    assert shown.status_code == 200, shown.text
    assert shown.json()["access"]["mode"] == "full"
    assert (folder / TRACKED_FILE).read_text(encoding="utf-8") == (Path(published["folder"]) / TRACKED_FILE).read_text(
        encoding="utf-8"
    )
    # Свой .git в папку не попал, история хранится в изолированном хранилище.
    assert not (folder / ".git").exists()
    assert (folder / ".hse-studio" / "git" / "HEAD").exists()


async def test__clone__studio_project__work_tree_is_clean_and_connected(
    target: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    folder = tmp_path / "clones" / "thesis"
    operation = await _clone(target, remote, folder)
    assert operation.status == "succeeded", operation

    dirty = run_git("status", "--porcelain", git_dir=folder / ".hse-studio" / "git", work_tree=folder)
    status = GitStatusResponse.model_validate(
        (await target.client.get(f"/api/v1/projects/{published['id']}/git")).json()
    )

    assert dirty == ""
    assert status.connected is True
    assert status.ui_state == "up_to_date"
    assert status.remote is not None
    assert (status.remote.branch, status.remote.local_branch, status.remote.kind) == ("main", "main", "file")
    assert (status.ahead, status.behind) == (0, 0)
    head = run_git("rev-parse", "HEAD", git_dir=folder / ".hse-studio" / "git")
    assert head == remote.head()


async def test__clone__studio_project__uses_branch_of_the_remote_and_keeps_history(
    target: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    folder = tmp_path / "clones" / "thesis"
    commits = run_git("rev-list", "--count", "main", git_dir=remote.path)

    operation = await _clone(target, remote, folder)

    assert operation.status == "succeeded", operation
    assert run_git("rev-list", "--count", "main", git_dir=folder / ".hse-studio" / "git") == commits
    assert run_git("symbolic-ref", "--short", "HEAD", git_dir=folder / ".hse-studio" / "git") == "main"


async def test__clone__folder_with_hidden_files_only__is_accepted_and_hidden_files_survive(
    target: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    folder = tmp_path / "clones" / "thesis"
    folder.mkdir(parents=True)
    (folder / ".DS_Store").write_bytes(b"x")

    operation = await _clone(target, remote, folder)

    assert operation.status == "succeeded", operation
    assert (folder / ".DS_Store").read_bytes() == b"x"
    assert (folder / TRACKED_FILE).exists()


async def test__clone__progress__is_monotonic_across_polls(
    target: Studio,
    remote: BareRemote,
    published: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = GitTransport.fetch

    async def slow_fetch(self: GitTransport, git_dir: Path, tgt: Any, **kwargs: Any) -> None:
        for percent in (5.0, 30.0, 30.0, 70.0):
            kwargs["on_progress"](percent, "Receiving objects")
            await asyncio.sleep(0.15)
        await original(self, git_dir, tgt, **kwargs)

    monkeypatch.setattr(GitTransport, "fetch", slow_fetch)
    resp = await _start(target, remote, tmp_path / "clones" / "thesis")
    operation_id = resp.json()["operation_id"]

    seen: list[float] = []
    phases: list[str] = []
    async with asyncio.timeout(_WAIT_S):
        while True:
            polled = OperationResponse.model_validate(
                (await target.client.get(f"/api/v1/git/operations/{operation_id}")).json()
            )
            if polled.phase == "download" and polled.percent is not None:
                seen.append(polled.percent)
            if not phases or phases[-1] != polled.phase:
                phases.append(polled.phase)
            if polled.status != "running":
                break
            await asyncio.sleep(0.03)

    assert polled.status == "succeeded", polled
    assert len(set(seen)) >= 2
    assert seen == sorted(seen)
    order = ["queued", "download", "verify", "register"]
    assert phases == [phase for phase in order if phase in phases]
    assert {"download", "verify", "register"} <= set(phases)


# --- отказы до записи в папку ---------------------------------------------------------------------


async def test__clone__not_a_studio_project__removes_the_created_folder(
    target: Studio, remote: BareRemote, tmp_path: Path
) -> None:
    seed_remote(remote, {"README.md": "just a repo"})
    folder = tmp_path / "clones" / "nested" / "repo"

    operation = await _clone(target, remote, folder)

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "not_a_studio_project"
    assert not (tmp_path / "clones").exists()
    assert (await target.client.get("/api/v1/projects")).json() == []


async def test__clone__not_a_studio_project__keeps_what_was_in_the_folder(
    target: Studio, remote: BareRemote, tmp_path: Path
) -> None:
    seed_remote(remote, {"README.md": "just a repo"})
    folder = tmp_path / "clones" / "repo"
    folder.mkdir(parents=True)
    (folder / ".keep").write_text("mine", encoding="utf-8")

    operation = await _clone(target, remote, folder)

    assert operation.error is not None
    assert operation.error.code == "not_a_studio_project"
    assert [entry.name for entry in folder.iterdir()] == [".keep"]
    assert (folder / ".keep").read_text(encoding="utf-8") == "mine"


async def test__clone__project_json_the_studio_cannot_load__not_a_studio_project_and_no_leftovers(
    target: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    _edit_project_json(published, lambda data: data.update(documents="x"))
    _commit(published, remote, "broken project file")
    folder = tmp_path / "clones" / "thesis"

    operation = await _clone(target, remote, folder)

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "not_a_studio_project"
    assert not folder.exists()


async def test__clone__empty_remote__fails_without_leftovers(
    target: Studio, remote: BareRemote, tmp_path: Path
) -> None:
    folder = tmp_path / "clones" / "empty"

    operation = await _clone(target, remote, folder)

    assert operation.error is not None
    assert operation.error.code == "not_a_studio_project"
    assert not folder.exists()


async def test__clone__unknown_branch__fails_with_branch_missing(
    target: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    folder = tmp_path / "clones" / "thesis"

    operation = await _clone(target, remote, folder, branch="nope")

    assert operation.error is not None
    assert operation.error.code == "branch_missing"
    assert not folder.exists()


async def test__clone__project_already_registered__fails_and_names_the_existing_folder(
    source: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    folder = tmp_path / "clones" / "second"

    operation = await _clone(source, remote, folder)

    assert operation.status == "failed"
    assert operation.error is not None
    assert operation.error.code == "project_exists"
    assert published["folder"] in operation.error.detail
    assert not folder.exists()
    assert len((await source.client.get("/api/v1/projects")).json()) == 1


async def test__clone__remote_with_symlink__is_refused_before_touching_the_folder(
    target: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    os.symlink("/etc/passwd", Path(published["folder"]) / "evil-link")
    _commit(published, remote, "link")
    folder = tmp_path / "clones" / "thesis"

    operation = await _clone(target, remote, folder)

    assert operation.error is not None
    assert operation.error.code == "git_error"
    assert "evil-link" in operation.error.detail
    assert not folder.exists()


async def test__clone__remote_tracks_the_private_store__is_refused(
    target: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    (_store(published) / "config").write_text("[core]\n\tfsmonitor = touch /tmp/pwned\n", encoding="utf-8")
    _commit(published, remote, "hostile store", force=True)
    folder = tmp_path / "clones" / "thesis"

    operation = await _clone(target, remote, folder)

    assert operation.error is not None
    assert operation.error.code == "git_error"
    assert ".hse-studio/git/config" in operation.error.detail
    assert not folder.exists()


# --- разрешённый доступ: схема и шаблон -----------------------------------------------------------


@pytest.mark.parametrize(
    ("schema", "access"),
    [
        ({"version": 2, "read_compat": 1, "write_compat": 2, "written_by": "9.9.9"}, "read_only"),
        ({"version": 3, "read_compat": 2, "write_compat": 3, "written_by": "9.9.9"}, "files_only"),
    ],
)
async def test__clone__newer_schema__is_cloned_with_limited_access(
    target: Studio,
    remote: BareRemote,
    published: dict[str, Any],
    tmp_path: Path,
    schema: dict[str, Any],
    access: str,
) -> None:
    _edit_project_json(published, lambda data: data.__setitem__("schema", schema))
    _commit(published, remote, "newer schema")
    folder = tmp_path / "clones" / "thesis"

    operation = await _clone(target, remote, folder)

    assert operation.status == "succeeded", operation
    assert operation.result is not None
    assert (operation.result.access, operation.result.required_studio) == (access, "9.9.9")
    assert (folder / TRACKED_FILE).exists()


async def test__clone__template_version_missing__is_read_only_with_warning(
    target: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    _edit_project_json(published, lambda data: data["lock"].__setitem__("version", "99.0.0"))
    _commit(published, remote, "unknown template version")
    folder = tmp_path / "clones" / "thesis"

    operation = await _clone(target, remote, folder)

    assert operation.status == "succeeded", operation
    result = operation.result
    assert result is not None
    assert result.access == "read_only"
    assert [warning.code for warning in result.warnings] == ["template_missing"]


# --- проверки запроса -----------------------------------------------------------------------------


async def test__clone__folder_not_empty__409_and_nothing_is_touched(
    target: Studio, remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    folder = tmp_path / "clones" / "busy"
    folder.mkdir(parents=True)
    (folder / "notes.txt").write_text("mine", encoding="utf-8")

    resp = await _start(target, remote, folder)

    assert resp.status_code == 409, resp.text
    assert _error(resp).code == "folder_not_empty"
    assert [entry.name for entry in folder.iterdir()] == ["notes.txt"]


async def test__clone__folder_inside_another_project__409(
    source: Studio, target: Studio, remote: BareRemote, published: dict[str, Any]
) -> None:
    resp = await _start(source, remote, Path(published["folder"]) / "sub")

    assert resp.status_code == 409, resp.text
    assert _error(resp).code == "folder_not_empty"
    assert not (Path(published["folder"]) / "sub").exists()


async def test__clone__registered_folder__409(source: Studio, remote: BareRemote, published: dict[str, Any]) -> None:
    resp = await _start(source, remote, Path(published["folder"]))

    assert resp.status_code == 409, resp.text
    assert _error(resp).code == "folder_not_empty"


async def test__clone__relative_folder__422(target: Studio, remote: BareRemote) -> None:
    resp = await _start(target, remote, Path("relative/dir"))

    assert resp.status_code == 422, resp.text


async def test__clone__without_profile__409_profile_required(
    remote: BareRemote, published: dict[str, Any], tmp_path: Path
) -> None:
    studio, close = await _open_studio(tmp_path / "anonymous", profile=False)
    try:
        resp = await _start(studio, remote, tmp_path / "clones" / "thesis")
    finally:
        await close()

    assert resp.status_code == 409, resp.text
    assert _error(resp).code == "profile_required"
    assert not (tmp_path / "clones").exists()


async def test__clone__bad_url__422(target: Studio, tmp_path: Path) -> None:
    resp = await target.client.post(
        "/api/v1/git/clone", json={"url": "ext::sh -c id", "folder": str(tmp_path / "clones" / "x")}
    )

    assert resp.status_code == 422, resp.text
    assert _error(resp).code in {"url_invalid", "url_scheme_forbidden"}


async def test__clone__unknown_credential__409(target: Studio, remote: BareRemote, tmp_path: Path) -> None:
    resp = await _start(target, remote, tmp_path / "clones" / "x", credential_id="00000000-0000-0000-0000-000000000001")

    assert resp.status_code == 409, resp.text
    assert _error(resp).code == "credentials_missing"


async def test__clone__second_clone_into_the_same_folder_while_running__409_sync_busy(
    target: Studio,
    remote: BareRemote,
    published: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def hang(self: GitTransport, git_dir: Path, tgt: Any, **kwargs: Any) -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(GitTransport, "fetch", hang)
    folder = tmp_path / "clones" / "thesis"
    first = await _start(target, remote, folder)
    assert first.status_code == 202, first.text

    second = await _start(target, remote, folder)

    assert second.status_code == 409, second.text
    assert _error(second).code in {"sync_busy", "folder_not_empty"}
    await target.client.post(f"/api/v1/git/operations/{first.json()['operation_id']}/cancel")
    await _finished(target, first.json()["operation_id"])


# --- отмена ---------------------------------------------------------------------------------------


async def test__clone__cancel_mid_download__removes_the_created_folder(
    target: Studio,
    remote: BareRemote,
    published: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def hang(self: GitTransport, git_dir: Path, tgt: Any, **kwargs: Any) -> None:
        assert git_dir.exists()
        await asyncio.sleep(3600)

    monkeypatch.setattr(GitTransport, "fetch", hang)
    folder = tmp_path / "clones" / "deep" / "thesis"
    resp = await _start(target, remote, folder)
    operation_id = resp.json()["operation_id"]
    async with asyncio.timeout(_WAIT_S):
        while not (folder / ".hse-studio" / "git").exists():
            await asyncio.sleep(_POLL_S)

    cancelled = await target.client.post(f"/api/v1/git/operations/{operation_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    operation = await _finished(target, operation_id)

    assert operation.status == "cancelled"
    assert not (tmp_path / "clones").exists()
    assert (await target.client.get("/api/v1/projects")).json() == []


async def test__clone__cancel_in_preexisting_folder__keeps_hidden_files_and_removes_the_rest(
    target: Studio,
    remote: BareRemote,
    published: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def hang(self: GitTransport, git_dir: Path, tgt: Any, **kwargs: Any) -> None:
        await asyncio.sleep(3600)

    monkeypatch.setattr(GitTransport, "fetch", hang)
    folder = tmp_path / "clones" / "thesis"
    folder.mkdir(parents=True)
    (folder / ".keep").write_text("mine", encoding="utf-8")
    resp = await _start(target, remote, folder)
    operation_id = resp.json()["operation_id"]
    async with asyncio.timeout(_WAIT_S):
        while not (folder / ".hse-studio" / "git").exists():
            await asyncio.sleep(_POLL_S)

    await target.client.post(f"/api/v1/git/operations/{operation_id}/cancel")
    operation = await _finished(target, operation_id)

    assert operation.status == "cancelled"
    assert [entry.name for entry in folder.iterdir()] == [".keep"]


# --- папка по умолчанию ---------------------------------------------------------------------------


async def test__clone_defaults__suggests_a_free_folder_named_after_the_project(target: Studio) -> None:
    resp = await target.client.get("/api/v1/git/clone/defaults", params={"name": "Моя курсовая / 2026"})

    assert resp.status_code == 200, resp.text
    folder = Path(resp.json()["folder"])
    assert folder.parent.name == "projects"
    assert "/" not in folder.name
    assert folder.name.startswith("Моя-курсовая")
    assert not folder.exists()


async def test__clone_defaults__without_name__uses_a_neutral_name(target: Studio) -> None:
    resp = await target.client.get("/api/v1/git/clone/defaults")

    assert resp.status_code == 200, resp.text
    assert Path(resp.json()["folder"]).name == "project"
