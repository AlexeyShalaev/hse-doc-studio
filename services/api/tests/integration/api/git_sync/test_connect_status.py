"""Подключение проекта к удалённому репозиторию и статус синхронизации через настоящий API.

Удалённые репозитории здесь локальные голые (file://) и git http-backend на 127.0.0.1: сеть не нужна,
git настоящий. «Выборку» (её делает следующий срез) тесты имитируют командой git fetch над хранилищем.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.schemas.git_sync import GitErrorBody, GitStatusResponse, OperationResponse, ProbeResponse
from hse_doc_studio.core.git_sync.entities import OperationKind, OperationStatus, SyncHealth
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry, IGitRemoteRegistry, IGitSyncStateRepository
from hse_doc_studio.infra.git_sync.repo_reader import GitRepoReader
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.git_remote import BareRemote, GitHttpServer, make_bare_remote, run_git, seed_remote
from tests.integration.api.vcs.conftest import create_project, edit_tracked_file

_PROFILE = {"name": "Анна Петрова", "email": "a.petrova@edu.hse.ru"}
_TOKEN = "pat-token-0123456789"
_BOT_EMAIL = "bot@hse-studio.local"


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
        yield Stack(client, container, tmp_path)
    await container.close()


@pytest_asyncio.fixture
async def client(stack: Stack) -> AsyncClient:
    resp = await stack.client.put("/api/v1/profile", json=_PROFILE)
    assert resp.status_code == 200, resp.text
    return stack.client


@pytest_asyncio.fixture
async def project(client: AsyncClient, tmp_path: Path) -> dict[str, Any]:
    return await create_project(client, tmp_path / "proj")


@pytest.fixture
def remote(tmp_path: Path) -> BareRemote:
    return make_bare_remote(tmp_path / "remotes" / "origin.git")


def _store(project: dict[str, Any]) -> Path:
    return Path(project["folder"]) / ".hse-studio" / "git"


def _git(project: dict[str, Any], *args: str, check: bool = True) -> str:
    return run_git(*args, git_dir=_store(project), work_tree=Path(project["folder"]), check=check)


def _publish(project: dict[str, Any], remote: BareRemote, branch: str = "main") -> None:
    """Отправить историю проекта в пустой удалённый репозиторий, как это сделали бы коллеги."""
    _git(project, "push", "--quiet", remote.url, f"master:refs/heads/{branch}")


def _fetch(project: dict[str, Any], remote: BareRemote, branch: str = "main") -> None:
    """То, что делает фоновая выборка: обновить отслеживаемую ветку."""
    _git(project, "fetch", "--quiet", remote.url, f"refs/heads/{branch}:refs/remotes/origin/{branch}")


def _snapshot(project: dict[str, Any], marker: str) -> None:
    edit_tracked_file(project, marker)
    _git(project, "add", "-A")
    _git(project, "-c", "user.name=Test", "-c", "user.email=t@test.local", "commit", "--quiet", "-m", marker)


async def _connect(client: AsyncClient, project: dict[str, Any], remote: BareRemote, **body: Any) -> Any:
    return await client.put(
        f"/api/v1/projects/{project['id']}/git/remote", json={"url": remote.url, "credential_id": None, **body}
    )


async def _status(client: AsyncClient, project: dict[str, Any]) -> GitStatusResponse:
    resp = await client.get(f"/api/v1/projects/{project['id']}/git")
    assert resp.status_code == 200, resp.text
    return GitStatusResponse.model_validate(resp.json())


def _error(resp: Any) -> GitErrorBody:
    return GitErrorBody.model_validate(resp.json())


# --- статус без удалённого репозитория ----------------------------------------------------------------------------


async def test__get_git_status__no_remote__is_quiet_and_valid(client: AsyncClient, project: dict[str, Any]) -> None:
    status = await _status(client, project)

    assert status.connected is False
    assert status.ui_state == "no_remote"
    assert status.remote is None
    assert (status.relation, status.health) == ("none", "ok")
    assert (status.ahead, status.behind, status.bot_authored_commits) == (0, 0, 0)
    assert status.profile_ok is True
    assert status.auto_fetch.enabled is True
    assert status.auto_fetch.interval_s == 300


async def test__get_git_status__unknown_project__404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000/git")

    assert resp.status_code == 404


async def test__get_git_status__without_profile__profile_not_ok(stack: Stack, tmp_path: Path) -> None:
    project = await create_project(stack.client, tmp_path / "proj")

    status = GitStatusResponse.model_validate((await stack.client.get(f"/api/v1/projects/{project['id']}/git")).json())

    assert status.profile_ok is False


async def test__get_git_status__no_remote__does_not_start_git(
    client: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    started: list[object] = []
    original = subprocess.run

    def spy(*args: Any, **kwargs: Any) -> Any:
        started.append(args[0] if args else kwargs.get("args"))
        return original(*args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)

    await _status(client, project)

    assert started == []


# --- подключение --------------------------------------------------------------------------------------------------


async def test__connect__empty_remote__first_push_is_ahead(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    resp = await _connect(client, project, remote)

    assert resp.status_code == 200, resp.text
    status = GitStatusResponse.model_validate(resp.json())
    assert status.connected is True
    assert status.ui_state == "ahead"
    assert status.relation == "remote_empty"
    assert status.remote is not None
    assert (status.remote.branch, status.remote.local_branch) == ("main", "master")
    assert status.remote.kind == "file"
    assert status.remote.credential is None
    assert status.ahead >= 1
    assert len(status.outgoing) == min(status.ahead, 5)
    assert status.operation is None
    assert status.last_fetch_ok_at is not None
    assert remote.head() is None


async def test__connect__empty_remote__bot_commits_are_counted_and_bot_email_hidden(
    stack: Stack, remote: BareRemote, tmp_path: Path
) -> None:
    # Проект создан до профиля, поэтому его корневой коммит подписан служебным ботом.
    project = await create_project(stack.client, tmp_path / "proj")
    await stack.client.put("/api/v1/profile", json=_PROFILE)

    status = GitStatusResponse.model_validate((await _connect(stack.client, project, remote)).json())

    assert status.bot_authored_commits >= 1
    assert all(commit.author_email is None for commit in status.outgoing)


async def test__connect__same_project__in_sync(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)

    resp = await _connect(client, project, remote)

    assert resp.status_code == 200, resp.text
    status = GitStatusResponse.model_validate(resp.json())
    assert status.ui_state == "up_to_date"
    assert (status.relation, status.ahead, status.behind) == ("in_sync", 0, 0)
    assert status.incoming == []
    assert status.outgoing == []
    assert status.bot_authored_commits == 0


async def test__connect__persists_in_store_config_and_state_file(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect(client, project, remote)

    assert _git(project, "config", "--get", "remote.origin.url") == remote.url
    state = json.loads((_store(project) / "hse-sync.json").read_text(encoding="utf-8"))
    assert (state["local_branch"], state["remote_branch"], state["remote_empty"]) == ("master", "main", True)
    assert state["pending"] is None


async def test__connect__is_registered_for_background_fetch(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    registry = await stack.get(IGitRemoteRegistry)

    await _connect(client, project, remote)

    assert [p.resolve() for p in await registry.list()] == [Path(project["folder"]).resolve()]


async def test__connect__other_project__refused_without_adopt(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, tmp_path: Path
) -> None:
    other = await create_project(client, tmp_path / "other")
    _publish(other, remote)

    resp = await _connect(client, project, remote, adopt="merge_remote")

    assert resp.status_code == 409
    body = _error(resp)
    assert (body.code, body.can_adopt) == ("unrelated_histories", False)
    assert "remote.origin.url" not in _git(project, "config", "--list")
    assert _git(project, "for-each-ref", "refs/remotes/") == ""


async def test__connect__not_a_studio_project(client: AsyncClient, project: dict[str, Any], remote: BareRemote) -> None:
    seed_remote(remote, {"README.md": "just a repo"})

    resp = await _connect(client, project, remote)

    assert resp.status_code == 409
    assert _error(resp).code == "not_a_studio_project"
    assert _git(project, "for-each-ref", "refs/remotes/") == ""


async def test__connect__same_id_without_merge_base__needs_adopt(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    project_json = (Path(project["folder"]) / ".hse-studio" / "project.json").read_text(encoding="utf-8")
    seed_remote(remote, {".hse-studio/project.json": project_json})

    refused = await _connect(client, project, remote)
    adopted = await _connect(client, project, remote, adopt="merge_remote")

    assert refused.status_code == 409
    body = _error(refused)
    assert (body.code, body.can_adopt) == ("unrelated_histories", True)
    assert adopted.status_code == 200, adopted.text
    status = GitStatusResponse.model_validate(adopted.json())
    assert status.ui_state == "diverged"
    assert status.behind == 1
    assert status.ahead >= 1
    assert json.loads((_store(project) / "hse-sync.json").read_text(encoding="utf-8"))["adopted_unrelated"] is True


async def test__connect__remote_schema_newer__refused(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    path = Path(project["folder"]) / ".hse-studio" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    remote_data = {**data, "schema": {"version": 9, "read_compat": 9, "write_compat": 9, "written_by": "9.0.0"}}
    seed_remote(remote, {".hse-studio/project.json": json.dumps(remote_data)})

    resp = await _connect(client, project, remote, adopt="merge_remote")

    assert resp.status_code == 409
    body = _error(resp)
    assert (body.code, body.required_studio) == ("remote_schema_newer", "9.0.0")


async def test__connect__twice__remote_exists(client: AsyncClient, project: dict[str, Any], remote: BareRemote) -> None:
    await _connect(client, project, remote)

    resp = await _connect(client, project, remote)

    assert resp.status_code == 409
    assert _error(resp).code == "remote_exists"


async def test__connect__without_profile__profile_required(stack: Stack, tmp_path: Path, remote: BareRemote) -> None:
    project = await create_project(stack.client, tmp_path / "proj")

    resp = await _connect(stack.client, project, remote)

    assert resp.status_code == 409
    assert _error(resp).code == "profile_required"


async def test__connect__unknown_credential__credentials_missing(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    resp = await _connect(client, project, remote, credential_id="9a8b7c6d-1e2f-4a3b-8c4d-5e6f7a8b9c0d")

    assert resp.status_code == 409
    assert _error(resp).code == "credentials_missing"


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("not a url", "url_invalid"),
        ("ext::sh -c id", "url_invalid"),
        ("ftp://example.com/a.git", "url_scheme_forbidden"),
    ],
)
async def test__connect__bad_url__422(client: AsyncClient, project: dict[str, Any], url: str, code: str) -> None:
    resp = await client.put(f"/api/v1/projects/{project['id']}/git/remote", json={"url": url, "credential_id": None})

    assert resp.status_code == 422
    assert _error(resp).code == code


async def test__connect__bad_adopt_value__422(client: AsyncClient, project: dict[str, Any], remote: BareRemote) -> None:
    resp = await _connect(client, project, remote, adopt="push_local")

    assert resp.status_code == 422


async def test__connect__unknown_branch__branch_missing(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    resp = await _connect(client, project, remote, branch="no-such-branch")

    assert resp.status_code == 409
    assert _error(resp).code == "branch_missing"


async def test__connect__missing_remote_branch__branch_missing(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)

    resp = await _connect(client, project, remote, remote_branch="draft")

    assert resp.status_code == 409
    assert _error(resp).code == "branch_missing"
    assert _git(project, "for-each-ref", "refs/remotes/") == ""


async def test__connect__remote_not_reachable__offline_and_project_untouched(
    client: AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    resp = await client.put(
        f"/api/v1/projects/{project['id']}/git/remote",
        json={"url": f"file://{tmp_path / 'nowhere.git'}", "credential_id": None},
    )

    assert resp.status_code == 502
    assert (await _status(client, project)).connected is False


async def test__connect__project_without_version_store__creates_it_first(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    shutil.rmtree(_store(project))

    resp = await _connect(client, project, remote)

    assert resp.status_code == 200, resp.text
    assert GitStatusResponse.model_validate(resp.json()).ui_state == "ahead"
    assert _git(project, "config", "--get", "remote.origin.url") == remote.url


async def test__connect__registers_connect_operation_that_ends(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    operations = await stack.get(IGitOperationRegistry)

    await _connect(client, project, remote)

    assert operations.is_busy(Path(project["folder"])) is False
    assert operations.current_for(UUID(project["id"])) is None


# --- состояния статуса --------------------------------------------------------------------------------------------


async def test__status__ahead_after_local_commit(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    _snapshot(project, "новая глава")

    status = await _status(client, project)

    assert (status.ui_state, status.relation, status.ahead, status.behind) == ("ahead", "ahead", 1, 0)
    assert [c.message for c in status.outgoing] == ["новая глава"]
    assert status.outgoing[0].kind == "manual"
    assert status.outgoing[0].short_id == status.outgoing[0].id[:7]


async def test__status__behind_after_remote_commit(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    seed_remote(remote, {"notes/from-colleague.txt": "hello"}, message="Заметка коллеги")
    _fetch(project, remote)

    status = await _status(client, project)

    assert (status.ui_state, status.relation, status.ahead, status.behind) == ("behind", "behind", 0, 1)
    assert status.behind_files == 1
    assert [c.message for c in status.incoming] == ["Заметка коллеги"]
    assert status.incoming[0].author_email is not None


async def test__status__diverged(client: AsyncClient, project: dict[str, Any], remote: BareRemote) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    _snapshot(project, "моя правка")
    seed_remote(remote, {"notes/from-colleague.txt": "hello"}, message="Правка коллеги")
    _fetch(project, remote)

    status = await _status(client, project)

    assert (status.ui_state, status.relation, status.ahead, status.behind) == ("diverged", "diverged", 1, 1)
    assert len(status.incoming) == 1
    assert len(status.outgoing) == 1


async def test__status__lists_are_capped_at_five(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    for index in range(7):
        _snapshot(project, f"правка {index}")

    status = await _status(client, project)

    assert status.ahead == 7
    assert len(status.outgoing) == 5
    assert status.outgoing[0].message == "правка 6"


async def test__status__unfetched_when_remote_has_content_but_tracking_is_gone(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    _git(project, "update-ref", "-d", "refs/remotes/origin/main")

    status = await _status(client, project)

    assert (status.ui_state, status.relation) == ("unfetched", "unfetched")


async def test__status__is_memoised_by_branch_tips(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    original = GitRepoReader.ahead_behind
    calls: list[tuple[str, str]] = []

    def counting(self: GitRepoReader, folder: Path, local: str, tracking: str) -> tuple[int, int]:
        calls.append((local, tracking))
        return original(self, folder, local, tracking)

    monkeypatch.setattr(GitRepoReader, "ahead_behind", counting)
    _snapshot(project, "правка")

    first = await _status(client, project)
    again = await _status(client, project)
    _snapshot(project, "ещё правка")
    third = await _status(client, project)

    assert again == first
    assert (first.ahead, third.ahead) == (1, 2)
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("health", "ui_state"),
    [
        (SyncHealth.unauthenticated, "auth_failed"),
        (SyncHealth.offline, "offline"),
        (SyncHealth.error, "error"),
        (SyncHealth.host_key_changed, "error"),
    ],
)
async def test__status__health_of_last_contact(
    stack: Stack,
    client: AsyncClient,
    project: dict[str, Any],
    remote: BareRemote,
    health: SyncHealth,
    ui_state: str,
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    states = await stack.get(IGitSyncStateRepository)
    folder = Path(project["folder"])
    current = states.get(folder)
    assert current is not None
    states.save(folder, replace(current, health=health))

    status = await _status(client, project)

    assert (status.ui_state, status.health) == (ui_state, health.value)


async def test__status__damaged_store__answers_instead_of_failing(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    (_store(project) / "HEAD").write_text("garbage\n", encoding="utf-8")

    resp = await client.get(f"/api/v1/projects/{project['id']}/git")

    assert resp.status_code == 200, resp.text
    assert GitStatusResponse.model_validate(resp.json()).connected is True


async def test__status__blocked_off_branch(client: AsyncClient, project: dict[str, Any], remote: BareRemote) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    _git(project, "branch", "draft")
    _git(project, "symbolic-ref", "HEAD", "refs/heads/draft")

    status = await _status(client, project)

    assert status.ui_state == "blocked"
    assert status.blocked is not None
    assert status.blocked.reason == "off_branch"


async def test__status__blocked_profile_required(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    assert (await client.delete("/api/v1/profile")).status_code == 200

    status = await _status(client, project)

    assert status.ui_state == "blocked"
    assert status.blocked is not None
    assert status.blocked.reason == "profile_required"
    assert status.profile_ok is False


async def test__status__blocked_read_only(client: AsyncClient, project: dict[str, Any], remote: BareRemote) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    path = Path(project["folder"]) / ".hse-studio" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema"] = {"version": 9, "read_compat": 1, "write_compat": 9, "written_by": "9.0.0"}
    path.write_text(json.dumps(data), encoding="utf-8")

    status = await _status(client, project)

    assert status.ui_state == "blocked"
    assert status.blocked is not None
    assert status.blocked.reason == "read_only"
    assert status.blocked.required_studio == "9.0.0"


async def test__read_only_project__status_is_readable_but_connect_and_settings_are_locked(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    path = Path(project["folder"]) / ".hse-studio" / "project.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema"] = {"version": 9, "read_compat": 1, "write_compat": 9, "written_by": "9.0.0"}
    path.write_text(json.dumps(data), encoding="utf-8")
    base = f"/api/v1/projects/{project['id']}/git"

    assert (await client.get(base)).status_code == 200
    assert (await client.put(f"{base}/remote", json={"url": remote.url, "credential_id": None})).status_code == 423
    assert (await client.patch(f"{base}/settings", json={"auto_fetch": False})).status_code == 423
    assert (await client.delete(f"{base}/remote")).status_code == 423


async def test__status__blocked_store_untrusted_and_connect_refuses(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    _git(project, "config", "core.fsmonitor", "/tmp/evil")

    status = await _status(client, project)

    assert status.ui_state == "blocked"
    assert status.blocked is not None
    assert status.blocked.reason == "store_untrusted"


async def test__connect__untrusted_store__refused(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _git(project, "config", "core.fsmonitor", "/tmp/evil")

    resp = await _connect(client, project, remote)

    assert resp.status_code == 409
    assert _error(resp).code == "store_untrusted"


async def test__status__running_operation_is_syncing(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    operations = await stack.get(IGitOperationRegistry)
    operation = operations.begin(OperationKind.sync, project_id=UUID(project["id"]), folder=Path(project["folder"]))

    status = await _status(client, project)
    operations.finish(operation.id)
    after = await _status(client, project)

    assert status.ui_state == "syncing"
    assert status.operation is not None
    assert status.operation.id == operation.id
    assert status.operation.kind == "sync"
    assert status.operation.cancellable is True
    assert after.ui_state == "up_to_date"


async def test__status__pending_conflicts_session_from_state_file(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    from hse_doc_studio.core.git_sync.entities import PendingSession

    _publish(project, remote)
    await _connect(client, project, remote)
    states = await stack.get(IGitSyncStateRepository)
    folder = Path(project["folder"])
    current = states.get(folder)
    assert current is not None
    states.save(folder, replace(current, pending=PendingSession("sess-1", 3, 2)))

    status = await _status(client, project)

    assert status.ui_state == "conflicts"
    assert status.pending is not None
    assert (status.pending.files_total, status.pending.files_open) == (3, 2)


async def test__status__auto_fetch_follows_general_setting_and_project_override(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect(client, project, remote)
    assert (await client.put("/api/v1/settings", json={"git_fetch_interval_s": 600})).status_code == 200

    general = await _status(client, project)
    own = GitStatusResponse.model_validate(
        (await client.patch(f"/api/v1/projects/{project['id']}/git/settings", json={"interval_s": 120})).json()
    )
    switched_off = await client.put("/api/v1/settings", json={"git_fetch_interval_s": 0})
    off = await _status(client, project)

    assert (general.auto_fetch.enabled, general.auto_fetch.interval_s) == (True, 600)
    assert own.auto_fetch.interval_s == 120
    assert switched_off.status_code == 200
    assert off.auto_fetch.enabled is False


# --- настройки проекта --------------------------------------------------------------------------------------------


async def test__patch_settings__changes_state_and_returns_status(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect(client, project, remote)
    url = f"/api/v1/projects/{project['id']}/git/settings"

    off = await client.patch(url, json={"auto_fetch": False})
    acknowledged = await client.patch(url, json={"shared_folder_ack": True})
    reset = await client.patch(url, json={"interval_s": 90})
    cleared = await client.patch(url, json={"interval_s": None})

    assert GitStatusResponse.model_validate(off.json()).auto_fetch.enabled is False
    assert acknowledged.status_code == 200
    assert GitStatusResponse.model_validate(reset.json()).auto_fetch.interval_s == 90
    assert GitStatusResponse.model_validate(cleared.json()).auto_fetch.interval_s == 300
    state = json.loads((_store(project) / "hse-sync.json").read_text(encoding="utf-8"))
    assert (state["auto_fetch"], state["shared_folder_ack"], state["fetch_interval_s"]) == (False, True, None)


async def test__get_git_status__project_in_synced_folder__reports_shared_folder_until_acknowledged(
    client: AsyncClient, tmp_path: Path, remote: BareRemote
) -> None:
    (tmp_path / "Sync" / ".stfolder").mkdir(parents=True)
    synced = await create_project(client, tmp_path / "Sync" / "paper")
    plain = await create_project(client, tmp_path / "plain")
    await _connect(client, synced, remote)

    before = await _status(client, synced)
    await client.patch(f"/api/v1/projects/{synced['id']}/git/settings", json={"shared_folder_ack": True})
    after = await _status(client, synced)

    assert before.shared_folder is not None
    assert (before.shared_folder.provider, before.shared_folder.acknowledged) == ("syncthing", False)
    assert after.shared_folder is not None
    assert after.shared_folder.acknowledged is True
    assert (await _status(client, plain)).shared_folder is None


async def test__patch_settings__interval_below_minimum__422(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect(client, project, remote)

    resp = await client.patch(f"/api/v1/projects/{project['id']}/git/settings", json={"interval_s": 10})

    assert resp.status_code == 422


async def test__patch_settings__not_connected__404(client: AsyncClient, project: dict[str, Any]) -> None:
    resp = await client.patch(f"/api/v1/projects/{project['id']}/git/settings", json={"auto_fetch": False})

    assert resp.status_code == 404


# --- отключение ---------------------------------------------------------------------------------------------------


async def test__disconnect__keeps_remote_and_credentials_and_clears_project(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    created = await client.post(
        "/api/v1/git/credentials", json={"kind": "pat", "label": "Токен", "host": "github.com", "token": _TOKEN}
    )
    credential_id = created.json()["id"]
    await _connect(client, project, remote, credential_id=credential_id)
    head_before = remote.head()

    resp = await client.delete(f"/api/v1/projects/{project['id']}/git/remote")

    assert resp.status_code == 204
    assert remote.head() == head_before
    assert [c["id"] for c in (await client.get("/api/v1/git/credentials")).json()] == [credential_id]
    assert (await _status(client, project)).connected is False
    assert not (_store(project) / "hse-sync.json").exists()
    assert _git(project, "config", "--get", "remote.origin.url", check=False) == ""
    assert _git(project, "for-each-ref", "refs/remotes/") == ""
    registry = await stack.get(IGitRemoteRegistry)
    assert await registry.list() == []


async def test__disconnect__forget_credential__deletes_unused_one(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    created = await client.post(
        "/api/v1/git/credentials", json={"kind": "pat", "label": "Токен", "host": "github.com", "token": _TOKEN}
    )
    await _connect(client, project, remote, credential_id=created.json()["id"])

    resp = await client.delete(f"/api/v1/projects/{project['id']}/git/remote", params={"forget_credential": "true"})

    assert resp.status_code == 204
    assert (await client.get("/api/v1/git/credentials")).json() == []


async def test__disconnect__forget_credential__keeps_one_used_by_another_project(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, tmp_path: Path
) -> None:
    other = await create_project(client, tmp_path / "other")
    other_remote = make_bare_remote(tmp_path / "remotes" / "other.git")
    created = await client.post(
        "/api/v1/git/credentials", json={"kind": "pat", "label": "Токен", "host": "github.com", "token": _TOKEN}
    )
    credential_id = created.json()["id"]
    await _connect(client, project, remote, credential_id=credential_id)
    await _connect(client, other, other_remote, credential_id=credential_id)

    await client.delete(f"/api/v1/projects/{project['id']}/git/remote", params={"forget_credential": "true"})

    assert [c["id"] for c in (await client.get("/api/v1/git/credentials")).json()] == [credential_id]


async def test__disconnect__not_connected__is_idempotent(client: AsyncClient, project: dict[str, Any]) -> None:
    resp = await client.delete(f"/api/v1/projects/{project['id']}/git/remote")

    assert resp.status_code == 204


async def test__disconnect__then_connect_again(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    await client.delete(f"/api/v1/projects/{project['id']}/git/remote")

    resp = await _connect(client, project, remote)

    assert resp.status_code == 200
    assert GitStatusResponse.model_validate(resp.json()).ui_state == "up_to_date"


async def test__disconnect__refused_while_operation_runs(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect(client, project, remote)
    operations = await stack.get(IGitOperationRegistry)
    running = operations.begin(OperationKind.sync, project_id=UUID(project["id"]), folder=Path(project["folder"]))

    resp = await client.delete(f"/api/v1/projects/{project['id']}/git/remote")

    assert resp.status_code == 409
    body = _error(resp)
    assert (body.code, body.operation_id) == ("sync_busy", running.id)


# --- перенос и удаление проекта -----------------------------------------------------------------------------------


async def test__move_project__refused_while_operation_runs(
    stack: Stack, client: AsyncClient, project: dict[str, Any], tmp_path: Path
) -> None:
    operations = await stack.get(IGitOperationRegistry)
    running = operations.begin(OperationKind.sync, project_id=UUID(project["id"]), folder=Path(project["folder"]))

    resp = await client.post(f"/api/v1/projects/{project['id']}/move", json={"folder": str(tmp_path / "moved")})

    assert resp.status_code == 409
    body = _error(resp)
    assert (body.code, body.operation_id) == ("sync_busy", running.id)
    assert Path(project["folder"]).exists()
    operations.finish(running.id)
    ok = await client.post(f"/api/v1/projects/{project['id']}/move", json={"folder": str(tmp_path / "moved")})
    assert ok.status_code == 200, ok.text


async def test__move_project__keeps_remote_registered_under_new_folder(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, tmp_path: Path
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    registry = await stack.get(IGitRemoteRegistry)

    await client.post(f"/api/v1/projects/{project['id']}/move", json={"folder": str(tmp_path / "moved")})

    assert [p.resolve() for p in await registry.list()] == [(tmp_path / "moved").resolve()]
    assert (await _status(client, project)).ui_state == "up_to_date"


async def test__unregister_project__refused_while_operation_runs_then_forgets_remote(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connect(client, project, remote)
    operations = await stack.get(IGitOperationRegistry)
    registry = await stack.get(IGitRemoteRegistry)
    running = operations.begin(OperationKind.sync, project_id=UUID(project["id"]), folder=Path(project["folder"]))

    refused = await client.delete(f"/api/v1/projects/{project['id']}")
    operations.finish(running.id)
    removed = await client.delete(f"/api/v1/projects/{project['id']}")

    assert refused.status_code == 409
    assert _error(refused).code == "sync_busy"
    assert removed.status_code == 204
    assert await registry.list() == []


# --- проверка адреса ----------------------------------------------------------------------------------------------


async def _probe(client: AsyncClient, remote: BareRemote, **body: Any) -> ProbeResponse:
    resp = await client.post("/api/v1/git/remote/probe", json={"url": remote.url, **body})
    assert resp.status_code == 200, resp.text
    return ProbeResponse.model_validate(resp.json())


async def test__probe__empty_remote(client: AsyncClient, remote: BareRemote) -> None:
    probe = await _probe(client, remote)

    assert (probe.ok, probe.reachable, probe.auth_ok, probe.empty) == (True, True, True, True)
    assert (probe.relation, probe.branches, probe.default_branch) == ("empty", [], None)
    assert probe.url.kind == "file"
    assert probe.project is None


async def test__probe__studio_project_without_local_project(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)

    probe = await _probe(client, remote)

    assert probe.relation == "studio_project"
    assert probe.default_branch == "main"
    assert probe.branches == ["main"]
    assert probe.project is not None
    assert str(probe.project.id) == project["id"]
    assert probe.schema_access == "full"
    assert probe.template_available is True
    assert probe.required_studio is None


async def test__probe__same_and_other_project(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, tmp_path: Path
) -> None:
    _publish(project, remote)
    other = await create_project(client, tmp_path / "other")

    same = await _probe(client, remote, project_id=project["id"])
    different = await _probe(client, remote, project_id=other["id"])

    assert same.relation == "same_project"
    assert different.relation == "other_project"


async def test__probe__not_a_studio_project(client: AsyncClient, remote: BareRemote) -> None:
    seed_remote(remote, {"README.md": "x"})

    probe = await _probe(client, remote)

    assert (probe.ok, probe.relation, probe.project) == (True, "not_studio_project", None)


async def test__probe__newer_schema_reports_required_studio(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    data = json.loads((Path(project["folder"]) / ".hse-studio" / "project.json").read_text(encoding="utf-8"))
    data["schema"] = {"version": 9, "read_compat": 9, "write_compat": 9, "written_by": "9.0.0"}
    seed_remote(remote, {".hse-studio/project.json": json.dumps(data)})

    probe = await _probe(client, remote)

    assert (probe.schema_access, probe.required_studio) == ("files_only", "9.0.0")


async def test__probe__missing_template_is_reported(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    data = json.loads((Path(project["folder"]) / ".hse-studio" / "project.json").read_text(encoding="utf-8"))
    data["lock"]["version"] = "99.0.0"
    seed_remote(remote, {".hse-studio/project.json": json.dumps(data)})

    probe = await _probe(client, remote)

    assert probe.template_available is False


async def test__probe__unreachable__ok_false_with_code(client: AsyncClient, tmp_path: Path) -> None:
    resp = await client.post("/api/v1/git/remote/probe", json={"url": f"file://{tmp_path / 'nowhere.git'}"})

    assert resp.status_code == 200
    probe = ProbeResponse.model_validate(resp.json())
    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code in {"not_found_or_no_access", "offline", "git_error"}
    assert probe.relation == "unknown"


async def test__probe__requested_branch_missing__ok_false(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)

    probe = await _probe(client, remote, branch="draft")

    assert probe.ok is False
    assert probe.error is not None
    assert probe.error.code == "branch_missing"
    assert probe.branches == ["main"]


async def test__probe__unknown_credential__credentials_missing(client: AsyncClient, remote: BareRemote) -> None:
    resp = await client.post(
        "/api/v1/git/remote/probe",
        json={"url": remote.url, "credential_id": "9a8b7c6d-1e2f-4a3b-8c4d-5e6f7a8b9c0d"},
    )

    assert resp.status_code == 409
    assert _error(resp).code == "credentials_missing"


async def test__probe__bad_url__422(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/git/remote/probe", json={"url": "javascript:alert(1)"})

    assert resp.status_code == 422


async def test__probe__strips_token_from_url_and_never_echoes_it(client: AsyncClient, remote: BareRemote) -> None:
    resp = await client.post(
        "/api/v1/git/remote/probe", json={"url": "https://user:ghp_SECRET1234567890@127.0.0.1:1/x.git"}
    )

    assert resp.status_code == 200
    assert "ghp_SECRET1234567890" not in resp.text
    probe = ProbeResponse.model_validate(resp.json())
    assert probe.url.token_stripped is True
    assert "@" not in probe.url.display_url


async def test__probe__unknown_project__404(client: AsyncClient, remote: BareRemote) -> None:
    resp = await client.post(
        "/api/v1/git/remote/probe",
        json={"url": remote.url, "project_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert resp.status_code == 404


# --- доступ по https с токеном ------------------------------------------------------------------------------------


@pytest.fixture
def http_remote(
    http_git_server_factory: Callable[..., GitHttpServer], monkeypatch: pytest.MonkeyPatch
) -> tuple[GitHttpServer, BareRemote]:
    monkeypatch.setattr(app_settings.git, "allow_insecure_http", True)
    server = http_git_server_factory(token=_TOKEN)
    return server, server.create_repo("origin.git")


async def _create_pat(client: AsyncClient, token: str = _TOKEN) -> str:
    resp = await client.post(
        "/api/v1/git/credentials", json={"kind": "pat", "label": "Токен", "host": "127.0.0.1", "token": token}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def test__connect__http_remote_with_token__binds_credential(
    client: AsyncClient, project: dict[str, Any], http_remote: tuple[GitHttpServer, BareRemote]
) -> None:
    server, bare = http_remote
    _publish(project, bare)
    credential_id = await _create_pat(client)

    resp = await client.put(
        f"/api/v1/projects/{project['id']}/git/remote",
        json={"url": server.url("origin.git"), "credential_id": credential_id, "insecure_http": True},
    )

    assert resp.status_code == 200, resp.text
    status = GitStatusResponse.model_validate(resp.json())
    assert status.ui_state == "up_to_date"
    assert status.remote is not None
    assert status.remote.kind == "http"
    assert status.remote.insecure_http is True
    assert status.remote.credential is not None
    assert str(status.remote.credential.id) == credential_id
    assert _git(project, "config", "--get", "hse.credential") == credential_id
    assert _TOKEN not in (_store(project) / "config").read_text(encoding="utf-8")
    assert _TOKEN not in (_store(project) / "hse-sync.json").read_text(encoding="utf-8")
    assert _TOKEN not in resp.text


async def test__connect__http_remote_without_token__credentials_missing(
    client: AsyncClient, project: dict[str, Any], http_remote: tuple[GitHttpServer, BareRemote]
) -> None:
    server, _ = http_remote

    resp = await client.put(
        f"/api/v1/projects/{project['id']}/git/remote",
        json={"url": server.url("origin.git"), "credential_id": None, "insecure_http": True},
    )

    assert resp.status_code == 409
    assert _error(resp).code == "credentials_missing"


async def test__connect__http_remote_with_wrong_token__auth_failed(
    client: AsyncClient, project: dict[str, Any], http_remote: tuple[GitHttpServer, BareRemote]
) -> None:
    server, _ = http_remote
    credential_id = await _create_pat(client, token="wrong-token-abcdefghij")

    resp = await client.put(
        f"/api/v1/projects/{project['id']}/git/remote",
        json={"url": server.url("origin.git"), "credential_id": credential_id, "insecure_http": True},
    )

    assert resp.status_code == 502
    body = _error(resp)
    assert body.code == "auth_failed"
    assert "wrong-token-abcdefghij" not in resp.text
    assert (await _status(client, project)).connected is False


@pytest.mark.usefixtures("remote_not_loopback")
async def test__connect__http_without_server_policy__forbidden(
    client: AsyncClient, project: dict[str, Any], http_git_server_factory: Callable[..., GitHttpServer]
) -> None:
    server = http_git_server_factory(token=_TOKEN)

    resp = await client.put(
        f"/api/v1/projects/{project['id']}/git/remote",
        json={"url": server.url("origin.git"), "credential_id": None, "insecure_http": True},
    )

    assert resp.status_code == 422
    assert _error(resp).code == "url_scheme_forbidden"


# --- операции -----------------------------------------------------------------------------------------------------


async def test__get_operation__running_then_finished(stack: Stack, client: AsyncClient) -> None:
    operations = await stack.get(IGitOperationRegistry)
    operation = operations.begin(OperationKind.clone, project_id=None, folder=None)

    running = await client.get(f"/api/v1/git/operations/{operation.id}")
    operations.finish(operation.id)
    finished = await client.get(f"/api/v1/git/operations/{operation.id}")

    assert OperationResponse.model_validate(running.json()).status == "running"
    done = OperationResponse.model_validate(finished.json())
    assert (done.status, done.kind, done.project_id) == ("succeeded", "clone", None)
    assert done.finished_at is not None
    assert done.cancellable is False


async def test__get_operation__unknown__404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/git/operations/op_nope")

    assert resp.status_code == 404


async def test__cancel_operation__cancels_attached_task(stack: Stack, client: AsyncClient) -> None:
    operations = await stack.get(IGitOperationRegistry)
    operation = operations.begin(OperationKind.sync, project_id=None, folder=None)
    task = asyncio.create_task(asyncio.sleep(30))
    operations.attach_task(operation.id, task)

    resp = await client.post(f"/api/v1/git/operations/{operation.id}/cancel")
    with pytest.raises(asyncio.CancelledError):
        await task

    assert resp.status_code == 200
    assert OperationResponse.model_validate(resp.json()).id == operation.id
    assert task.cancelled()


async def test__cancel_operation__not_cancellable__409(stack: Stack, client: AsyncClient) -> None:
    operations = await stack.get(IGitOperationRegistry)
    operation = operations.begin(OperationKind.sync, project_id=None, folder=None)
    operations.update(operation.id, cancellable=False)

    resp = await client.post(f"/api/v1/git/operations/{operation.id}/cancel")

    assert resp.status_code == 409
    assert _error(resp).code == "operation_not_cancellable"
    assert operations.get(operation.id) is not None
    assert operations.get(operation.id).status is OperationStatus.running  # type: ignore[union-attr]


async def test__cancel_operation__finished__409_and_unknown__404(stack: Stack, client: AsyncClient) -> None:
    operations = await stack.get(IGitOperationRegistry)
    operation = operations.begin(OperationKind.sync, project_id=None, folder=None)
    operations.finish(operation.id)

    finished = await client.post(f"/api/v1/git/operations/{operation.id}/cancel")
    unknown = await client.post("/api/v1/git/operations/op_nope/cancel")

    assert finished.status_code == 409
    assert unknown.status_code == 404


async def test__open_existing_folder_with_a_remote__is_registered_for_background_fetch_at_once(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)
    registry = await stack.get(IGitRemoteRegistry)
    # Реестр уже просмотрен; папку убирают из списка проектов и открывают снова, как скопированную с другого компьютера.
    assert (await client.delete(f"/api/v1/projects/{project['id']}")).status_code == 204
    assert await registry.list() == []

    resp = await client.post("/api/v1/projects/connect", json={"folder": project["folder"]})

    assert resp.status_code == 201, resp.text
    assert [p.resolve() for p in await registry.list()] == [Path(project["folder"]).resolve()]
