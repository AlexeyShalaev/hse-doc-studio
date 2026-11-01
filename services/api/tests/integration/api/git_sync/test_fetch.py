"""Выборка из удалённого репозитория: кнопка (POST /git/fetch) и фоновый тик расписания через настоящий API.

Удалённые репозитории локальные голые (file://), git настоящий. Отказы сети и доступа подставляются в
GitTransport.fetch, чтобы они были точными и быстрыми; всё остальное идёт по-настоящему.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from hse_doc_studio.api.schemas.git_sync import GitErrorBody, GitStatusResponse
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind, OperationKind
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.fetch_schedule import FetchBook
from hse_doc_studio.core.git_sync.protocols import (
    IGitCredentialRepository,
    IGitOperationRegistry,
    IGitRemoteRegistry,
    IGitStoreGuard,
    IGitSyncStateRepository,
)
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.infra.git_sync.git_remote_runner import GitRemoteRunner
from hse_doc_studio.infra.git_sync.git_transport import GitTransport
from hse_doc_studio.infra.git_sync.store_remotes import GitStoreRemotes
from hse_doc_studio.use_cases.git_sync.fetch_all_remotes import FetchAllGitRemotesUC, FetchTickResult
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.git_remote import BareRemote, make_bare_remote, run_git, seed_remote
from tests.integration.api.vcs.conftest import create_project

_PROFILE = {"name": "Анна Петрова", "email": "a.petrova@edu.hse.ru"}
_INTERVAL_S = 300
# Больше самого длинного разброса периода (+10%), чтобы «прошёл период» не зависело от пути проекта.
_PERIOD_PASSED = timedelta(seconds=_INTERVAL_S * 1.1 + 1)
_CREDENTIAL_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@dataclass
class Stack:
    client: AsyncClient
    container: Any
    tmp_path: Path

    async def get[T](self, kind: type[T]) -> T:
        return await self.container.get(kind)  # type: ignore[no-any-return]


class Clock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class FetchSpy:
    """Считает вызовы GitTransport.fetch; `errors` по очереди подменяют настоящую выборку отказом."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls = 0
        self.errors: list[GitSyncError | None] = []
        original = GitTransport.fetch

        async def spy(transport: GitTransport, *args: Any, **kwargs: Any) -> None:
            self.calls += 1
            if self.errors:
                error = self.errors.pop(0)
                if error is not None:
                    raise error
            await original(transport, *args, **kwargs)

        monkeypatch.setattr(GitTransport, "fetch", spy)

    def fail(self, code: GitErrorCode, times: int = 1) -> None:
        self.errors.extend(GitSyncError(code, f"{code.value} (test)") for _ in range(times))


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


def _publish(project: dict[str, Any], remote: BareRemote) -> None:
    run_git(
        "push",
        "--quiet",
        remote.url,
        "master:refs/heads/main",
        git_dir=_store(project),
        work_tree=Path(project["folder"]),
    )


async def _connect(client: AsyncClient, project: dict[str, Any], remote: BareRemote) -> None:
    resp = await client.put(
        f"/api/v1/projects/{project['id']}/git/remote", json={"url": remote.url, "credential_id": None}
    )
    assert resp.status_code == 200, resp.text


async def _connected(client: AsyncClient, project: dict[str, Any], remote: BareRemote) -> None:
    _publish(project, remote)
    await _connect(client, project, remote)


def _fetch_url(project: dict[str, Any]) -> str:
    return f"/api/v1/projects/{project['id']}/git/fetch"


async def _post_fetch(client: AsyncClient, project: dict[str, Any]) -> GitStatusResponse:
    resp = await client.post(_fetch_url(project))
    assert resp.status_code == 200, resp.text
    return GitStatusResponse.model_validate(resp.json())


async def _status(client: AsyncClient, project: dict[str, Any]) -> GitStatusResponse:
    resp = await client.get(f"/api/v1/projects/{project['id']}/git")
    assert resp.status_code == 200, resp.text
    return GitStatusResponse.model_validate(resp.json())


async def _age_fetch(stack: Stack, project: dict[str, Any], by: timedelta) -> None:
    """Состарить последнюю выборку, как будто с неё прошло время: проверять срок по настоящим часам долго."""
    states = await stack.get(IGitSyncStateRepository)
    folder = Path(project["folder"])
    state = states.get(folder)
    assert state is not None
    assert state.last_fetch_at is not None
    states.save(
        folder,
        replace(
            state,
            last_fetch_at=state.last_fetch_at - by,
            last_fetch_ok_at=(state.last_fetch_ok_at - by) if state.last_fetch_ok_at else None,
        ),
    )


async def _tick(stack: Stack, clock: Clock) -> FetchTickResult:
    async with stack.container() as request_container:
        uc = await request_container.get(FetchAllGitRemotesUC)
        uc._clock = clock  # noqa: SLF001 — часы подменяются, чтобы срок проверялся без ожидания
        uc._fetch._clock = clock  # noqa: SLF001
        return await uc.run_once()


# --- кнопка: POST /git/fetch --------------------------------------------------------------------------------------


async def test__post_fetch__no_remote__returns_quiet_status_without_git(
    client: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = FetchSpy(monkeypatch)

    status = await _post_fetch(client, project)

    assert (status.connected, status.ui_state) == (False, "no_remote")
    assert spy.calls == 0


async def test__post_fetch__unknown_project__404(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/projects/00000000-0000-0000-0000-000000000000/git/fetch")

    assert resp.status_code == 404


async def test__post_fetch__teammate_pushed__behind_badge_data_appears(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack
) -> None:
    await _connected(client, project, remote)
    assert (await _status(client, project)).ui_state == "up_to_date"
    seed_remote(remote, {"notes/from-colleague.txt": "hello"}, message="Заметка коллеги")
    await _age_fetch(stack, project, timedelta(minutes=1))

    status = await _post_fetch(client, project)

    assert (status.ui_state, status.relation, status.ahead, status.behind) == ("behind", "behind", 0, 1)
    assert status.behind_files == 1
    assert [c.message for c in status.incoming] == ["Заметка коллеги"]
    assert status.health == "ok"
    assert status.last_error is None
    assert status.last_fetch_ok_at is not None


async def test__post_fetch__second_call_within_fifteen_seconds__does_not_start_git(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    spy = FetchSpy(monkeypatch)

    await _post_fetch(client, project)
    await _post_fetch(client, project)

    # Подключение только что выбирало ветку, поэтому и первая просьба укладывается в окно.
    assert spy.calls == 0


async def test__post_fetch__after_the_debounce_window__fetches_again(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    spy = FetchSpy(monkeypatch)
    await _age_fetch(stack, project, timedelta(seconds=20))

    await _post_fetch(client, project)
    await _post_fetch(client, project)

    assert spy.calls == 1


async def test__post_fetch__empty_remote__stays_a_first_push_and_is_healthy(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack
) -> None:
    await _connect(client, project, remote)
    await _age_fetch(stack, project, timedelta(minutes=1))

    status = await _post_fetch(client, project)

    assert (status.ui_state, status.relation, status.health) == ("ahead", "remote_empty", "ok")
    assert status.last_error is None


async def test__post_fetch__empty_remote_gets_its_first_push__compares_with_it(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack
) -> None:
    await _connect(client, project, remote)
    _publish(project, remote)
    await _age_fetch(stack, project, timedelta(minutes=1))

    status = await _post_fetch(client, project)

    assert (status.ui_state, status.relation, status.ahead, status.behind) == ("up_to_date", "in_sync", 0, 0)


@pytest.mark.parametrize(
    ("code", "health", "ui_state"),
    [
        (GitErrorCode.offline, "offline", "offline"),
        (GitErrorCode.timeout, "offline", "offline"),
        (GitErrorCode.auth_failed, "unauthenticated", "auth_failed"),
        (GitErrorCode.not_found_or_no_access, "remote_missing", "error"),
        (GitErrorCode.tls_error, "error", "error"),
    ],
)
async def test__post_fetch__upstream_failure__is_a_status_not_an_error(
    client: AsyncClient,
    project: dict[str, Any],
    remote: BareRemote,
    stack: Stack,
    monkeypatch: pytest.MonkeyPatch,
    code: GitErrorCode,
    health: str,
    ui_state: str,
) -> None:
    await _connected(client, project, remote)
    await _age_fetch(stack, project, timedelta(minutes=1))
    FetchSpy(monkeypatch).fail(code)

    status = await _post_fetch(client, project)

    assert (status.health, status.ui_state) == (health, ui_state)
    assert status.last_error is not None
    assert status.last_error.code == code.value
    assert status.last_fetch_at is not None


async def test__post_fetch__recovers_after_a_failure(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    await _age_fetch(stack, project, timedelta(minutes=1))
    spy = FetchSpy(monkeypatch)
    spy.fail(GitErrorCode.offline)
    assert (await _post_fetch(client, project)).health == "offline"

    # Сбой не считается удачной выборкой, поэтому повтор по просьбе человека не упирается в окно.
    status = await _post_fetch(client, project)

    assert (status.health, status.ui_state, status.last_error) == ("ok", "up_to_date", None)
    assert spy.calls == 2


async def test__post_fetch__running_operation__409_sync_busy_with_its_id(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack
) -> None:
    await _connected(client, project, remote)
    operations = await stack.get(IGitOperationRegistry)
    operation = operations.begin(OperationKind.sync, project_id=UUID(project["id"]), folder=Path(project["folder"]))

    resp = await client.post(_fetch_url(project))

    assert resp.status_code == 409
    body = GitErrorBody.model_validate(resp.json())
    assert body.code == "sync_busy"
    assert body.operation_id == operation.id


async def test__post_fetch__remote_written_by_a_newer_studio__blocks_with_required_version(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack
) -> None:
    await _connected(client, project, remote)
    raw = json.loads((Path(project["folder"]) / ".hse-studio" / "project.json").read_text(encoding="utf-8"))
    raw["schema"] = {"version": 999, "read_compat": 999, "write_compat": 999, "written_by": "99.0.0"}
    seed_remote(remote, {".hse-studio/project.json": json.dumps(raw)}, message="Проект открыт новой Студией")
    await _age_fetch(stack, project, timedelta(minutes=1))

    status = await _post_fetch(client, project)

    assert status.ui_state == "blocked"
    assert status.blocked is not None
    assert (status.blocked.reason, status.blocked.required_studio) == ("remote_schema_newer", "99.0.0")


async def test__post_fetch__newer_schema_is_replaced_by_a_normal_tip__unblocks(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack
) -> None:
    await _connected(client, project, remote)
    path = Path(project["folder"]) / ".hse-studio" / "project.json"
    original = path.read_text(encoding="utf-8")
    newer = json.loads(original)
    newer["schema"] = {"version": 999, "read_compat": 999, "write_compat": 999, "written_by": "99.0.0"}
    seed_remote(remote, {".hse-studio/project.json": json.dumps(newer)}, message="новая Студия")
    await _age_fetch(stack, project, timedelta(minutes=1))
    assert (await _post_fetch(client, project)).ui_state == "blocked"
    seed_remote(remote, {".hse-studio/project.json": original}, message="вернули схему")
    await _age_fetch(stack, project, timedelta(minutes=1))

    status = await _post_fetch(client, project)

    assert status.blocked is None
    assert status.ui_state == "behind"


async def test__post_fetch__does_not_touch_the_project_tree_or_take_the_folder(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack
) -> None:
    await _connected(client, project, remote)
    seed_remote(remote, {"notes/from-colleague.txt": "hello"}, message="Заметка коллеги")
    await _age_fetch(stack, project, timedelta(minutes=1))

    await _post_fetch(client, project)

    assert not (Path(project["folder"]) / "notes" / "from-colleague.txt").exists()


# --- расписание: тик ----------------------------------------------------------------------------------------------


async def test__tick__no_remotes__never_starts_git(
    stack: Stack, client: AsyncClient, project: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[object] = []

    async def forbidden(*args: Any, **kwargs: Any) -> None:
        started.append(args)
        raise AssertionError("git must not be started without connected remotes")

    monkeypatch.setattr(GitRemoteRunner, "run", forbidden)
    monkeypatch.setattr(GitRemoteRunner, "run_local", forbidden)

    result = await _tick(stack, Clock())

    assert result == FetchTickResult()
    assert started == []


async def test__tick__project_is_not_due_yet__is_left_alone(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    spy = FetchSpy(monkeypatch)

    result = await _tick(stack, Clock())

    assert (result.registered, result.fetched, result.skipped) == (1, 0, 1)
    assert spy.calls == 0


async def test__tick__after_the_period__fetches_and_the_badge_data_appears(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    seed_remote(remote, {"notes/from-colleague.txt": "hello"}, message="Заметка коллеги")
    spy = FetchSpy(monkeypatch)
    clock = Clock()
    clock.advance(_PERIOD_PASSED)

    result = await _tick(stack, clock)

    assert (result.registered, result.fetched, result.failed) == (1, 1, 0)
    assert spy.calls == 1
    status = await _status(client, project)
    assert (status.ui_state, status.behind) == ("behind", 1)
    assert status.last_fetch_ok_at is not None
    assert status.last_fetch_ok_at.replace(tzinfo=UTC) >= clock.now - timedelta(seconds=1)


async def test__tick__fetched_project__is_not_fetched_again_until_the_next_period(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    spy = FetchSpy(monkeypatch)
    clock = Clock()
    clock.advance(_PERIOD_PASSED)
    await _tick(stack, clock)

    clock.advance(timedelta(seconds=_INTERVAL_S * 0.8))
    await _tick(stack, clock)
    assert spy.calls == 1

    clock.advance(_PERIOD_PASSED)
    await _tick(stack, clock)
    assert spy.calls == 2


async def test__tick__offline_failures__back_off_exponentially(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    spy = FetchSpy(monkeypatch)
    spy.fail(GitErrorCode.offline, times=10)
    clock = Clock()
    clock.advance(_PERIOD_PASSED)

    first = await _tick(stack, clock)
    assert (first.failed, spy.calls) == (1, 1)
    # Одной задержки в период после сбоя мало: после первого она вдвое длиннее.
    clock.advance(_PERIOD_PASSED)
    await _tick(stack, clock)
    assert spy.calls == 1
    clock.advance(_PERIOD_PASSED)
    second = await _tick(stack, clock)
    assert (second.failed, spy.calls) == (1, 2)
    # После второго сбоя ждать надо уже вчетверо дольше периода.
    clock.advance(_PERIOD_PASSED * 3)
    await _tick(stack, clock)
    assert spy.calls == 2
    clock.advance(_PERIOD_PASSED)
    await _tick(stack, clock)
    assert spy.calls == 3
    status = await _status(client, project)
    assert (status.health, status.ui_state) == ("offline", "offline")


async def test__tick__success_after_failures__returns_to_the_normal_period(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    spy = FetchSpy(monkeypatch)
    spy.fail(GitErrorCode.offline, times=2)
    clock = Clock()
    for _ in range(3):
        clock.advance(_PERIOD_PASSED * 4)
        await _tick(stack, clock)
    assert spy.calls == 3

    clock.advance(_PERIOD_PASSED)
    await _tick(stack, clock)

    assert spy.calls == 4
    assert (await _status(client, project)).health == "ok"


async def test__tick__auth_failed__stops_the_background_fetch(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    spy = FetchSpy(monkeypatch)
    spy.fail(GitErrorCode.auth_failed)
    clock = Clock()
    clock.advance(_PERIOD_PASSED)

    first = await _tick(stack, clock)
    assert (first.failed, spy.calls) == (1, 1)
    for _ in range(5):
        clock.advance(timedelta(hours=6))
        await _tick(stack, clock)

    assert spy.calls == 1
    assert (await _status(client, project)).ui_state == "auth_failed"


async def test__tick__auth_failed__the_button_still_works_and_heals_it(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    spy = FetchSpy(monkeypatch)
    spy.fail(GitErrorCode.auth_failed)
    clock = Clock()
    clock.advance(_PERIOD_PASSED)
    await _tick(stack, clock)

    status = await _post_fetch(client, project)
    assert (status.health, status.ui_state) == ("ok", "up_to_date")

    clock.advance(_PERIOD_PASSED)
    await _tick(stack, clock)
    assert spy.calls == 3


async def test__tick__auth_failed_then_the_token_is_replaced__tries_again(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    credentials = await stack.get(IGitCredentialRepository)
    credential = GitCredential(
        id=_CREDENTIAL_ID,
        kind=GitCredentialKind.pat,
        label="токен",
        host="example.com",
        username=None,
        status=CredentialStatus.unverified,
        created_at=datetime.now(UTC),
    )
    await credentials.add(credential, Secret("pat-token-0123456789"))
    states = await stack.get(IGitSyncStateRepository)
    folder = Path(project["folder"])
    state = states.get(folder)
    assert state is not None
    states.save(folder, replace(state, credential_id=credential.id))
    spy = FetchSpy(monkeypatch)
    spy.fail(GitErrorCode.auth_failed)
    clock = Clock()
    clock.advance(_PERIOD_PASSED)
    await _tick(stack, clock)
    await credentials.mark(credential.id, CredentialStatus.auth_failed)
    clock.advance(timedelta(hours=1))
    await _tick(stack, clock)
    assert spy.calls == 1

    await credentials.update(
        replace(credential, status=CredentialStatus.unverified), Secret("pat-new-token-9876543210")
    )
    clock.advance(timedelta(hours=1))
    result = await _tick(stack, clock)

    assert (result.fetched, spy.calls) == (1, 2)


async def test__tick__interval_setting_zero__disables_the_background_fetch(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    assert (await client.put("/api/v1/settings", json={"git_fetch_interval_s": 0})).status_code == 200
    spy = FetchSpy(monkeypatch)
    clock = Clock()
    clock.advance(timedelta(days=2))

    result = await _tick(stack, clock)

    assert (result.registered, result.fetched, spy.calls) == (1, 0, 0)


async def test__tick__project_auto_fetch_off__is_skipped_but_the_button_works(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    resp = await client.patch(f"/api/v1/projects/{project['id']}/git/settings", json={"auto_fetch": False})
    assert resp.status_code == 200, resp.text
    spy = FetchSpy(monkeypatch)
    clock = Clock()
    clock.advance(timedelta(days=2))

    await _tick(stack, clock)
    assert spy.calls == 0

    await _age_fetch(stack, project, timedelta(minutes=1))
    await _post_fetch(client, project)
    assert spy.calls == 1


async def test__tick__project_interval_overrides_the_general_one(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    resp = await client.patch(f"/api/v1/projects/{project['id']}/git/settings", json={"interval_s": 3600})
    assert resp.status_code == 200, resp.text
    spy = FetchSpy(monkeypatch)
    clock = Clock()
    clock.advance(_PERIOD_PASSED)

    await _tick(stack, clock)
    assert spy.calls == 0

    clock.advance(timedelta(hours=1, minutes=10))
    await _tick(stack, clock)
    assert spy.calls == 1


async def test__tick__running_operation__skips_the_project(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    operations = await stack.get(IGitOperationRegistry)
    operations.begin(OperationKind.sync, project_id=UUID(project["id"]), folder=Path(project["folder"]))
    spy = FetchSpy(monkeypatch)
    clock = Clock()
    clock.advance(timedelta(days=1))

    result = await _tick(stack, clock)

    assert (result.fetched, spy.calls) == (0, 0)


async def test__tick__one_broken_project__does_not_stop_the_others(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote, tmp_path: Path
) -> None:
    other = await create_project(client, tmp_path / "other")
    other_remote = make_bare_remote(tmp_path / "remotes" / "other.git")
    await _connected(client, project, remote)
    await _connected(client, other, other_remote)
    for item in (project, other):
        await _age_fetch(stack, item, timedelta(hours=1))
    seed_remote(other_remote, {"a.txt": "x"}, message="коллега")
    broken = (Path(project["folder"]) / ".hse-studio" / "project.json").read_bytes()
    (Path(project["folder"]) / ".hse-studio" / "project.json").write_text("{не json", encoding="utf-8")
    try:
        result = await _tick(stack, Clock())
    finally:
        (Path(project["folder"]) / ".hse-studio" / "project.json").write_bytes(broken)

    assert result.registered == 2
    assert (await _status(client, other)).behind == 1


async def test__tick__project_without_remote_any_more__is_dropped_from_the_registry(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    await _connected(client, project, remote)
    registry = await stack.get(IGitRemoteRegistry)
    assert len(await registry.list()) == 1
    run_git("remote", "remove", "origin", git_dir=_store(project))
    # Подключение читается, когда проекту пора на выборку: до этого тик не запускает git ради каждого проекта.
    await _age_fetch(stack, project, _PERIOD_PASSED)

    await _tick(stack, Clock())

    assert await registry.list() == []


async def test__connect__wakes_the_background_fetch(
    stack: Stack, client: AsyncClient, project: dict[str, Any], remote: BareRemote
) -> None:
    registry = await stack.get(IGitRemoteRegistry)
    woken: list[int] = []
    registry.subscribe(lambda: woken.append(1))

    await _connected(client, project, remote)

    assert woken == [1]


# --- выборка идёт долго: просьбы, отключение, перенос, синхронизация --------------------------------------------------


class ParkedFetch:
    """Выборка, которая стоит, пока тест её не отпустит; считает вызовы и одновременно идущие выборки."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, error: GitSyncError | None = None) -> None:
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        original = GitTransport.fetch

        async def parked(transport: GitTransport, *args: Any, **kwargs: Any) -> None:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.entered.set()
            try:
                await self.release.wait()
                if error is not None:
                    raise error
                await original(transport, *args, **kwargs)
            finally:
                self.active -= 1

        monkeypatch.setattr(GitTransport, "fetch", parked)

    async def started(self) -> None:
        async with asyncio.timeout(10):
            await self.entered.wait()


async def test__post_fetch__requests_while_a_fetch_is_running__join_it_instead_of_queueing(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    await _age_fetch(stack, project, timedelta(minutes=1))
    parked = ParkedFetch(monkeypatch, error=GitSyncError(GitErrorCode.timeout, "black hole"))
    requests = [asyncio.create_task(client.post(_fetch_url(project))) for _ in range(3)]
    await parked.started()
    await asyncio.sleep(0.3)

    parked.release.set()
    responses = await asyncio.gather(*requests)

    assert [resp.status_code for resp in responses] == [200, 200, 200]
    assert {GitStatusResponse.model_validate(resp.json()).health for resp in responses} == {"offline"}
    assert parked.calls == 1


async def test__disconnect__while_a_fetch_is_running__nothing_of_the_old_remote_comes_back(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    await _age_fetch(stack, project, timedelta(minutes=1))
    parked = ParkedFetch(monkeypatch)
    fetching = asyncio.create_task(client.post(_fetch_url(project)))
    await parked.started()
    disconnecting = asyncio.create_task(client.delete(f"/api/v1/projects/{project['id']}/git/remote"))
    await asyncio.sleep(0.3)
    assert not disconnecting.done()

    parked.release.set()
    await fetching
    resp = await disconnecting

    assert resp.status_code == 204
    assert not (_store(project) / "hse-sync.json").exists()
    tracking = run_git(
        "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main", git_dir=_store(project), check=False
    )
    assert tracking == ""
    assert Path(project["folder"]) not in await (await stack.get(IGitRemoteRegistry)).list()


async def test__move__while_a_fetch_is_running__the_old_location_does_not_reappear(
    client: AsyncClient,
    project: dict[str, Any],
    remote: BareRemote,
    stack: Stack,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _connected(client, project, remote)
    await _age_fetch(stack, project, timedelta(minutes=1))
    parked = ParkedFetch(monkeypatch)
    fetching = asyncio.create_task(client.post(_fetch_url(project)))
    await parked.started()
    moving = asyncio.create_task(
        client.post(f"/api/v1/projects/{project['id']}/move", json={"folder": str(tmp_path / "moved")})
    )
    await asyncio.sleep(0.3)
    assert not moving.done()

    parked.release.set()
    await fetching
    resp = await moving

    assert resp.status_code == 200, resp.text
    assert not Path(project["folder"]).exists()
    assert (tmp_path / "moved" / ".hse-studio" / "git" / "hse-sync.json").exists()


async def test__sync__while_a_background_fetch_is_running__waits_for_it_instead_of_racing_on_the_ref(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    await _age_fetch(stack, project, timedelta(minutes=1))
    parked = ParkedFetch(monkeypatch)
    fetching = asyncio.create_task(client.post(_fetch_url(project)))
    await parked.started()
    started = await client.post(f"/api/v1/projects/{project['id']}/git/sync", json={})
    assert started.status_code == 202, started.text
    await asyncio.sleep(0.3)

    parked.release.set()
    await fetching
    async with asyncio.timeout(60):
        while True:
            operation = (await client.get(f"/api/v1/git/operations/{started.json()['operation_id']}")).json()
            if operation["status"] != "running":
                break
            await asyncio.sleep(0.05)

    assert operation["status"] == "succeeded", operation
    assert parked.max_active == 1


async def test__sync__after_failures__resets_the_background_fetch_delay(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack
) -> None:
    await _connected(client, project, remote)
    book = await stack.get(FetchBook)
    folder = Path(project["folder"])
    book.failed(folder)
    book.failed(folder)
    await _age_fetch(stack, project, timedelta(minutes=1))

    resp = await client.post(f"/api/v1/projects/{project['id']}/git/sync", json={})
    assert resp.status_code == 202, resp.text
    async with asyncio.timeout(60):
        while book.failures(folder):
            await asyncio.sleep(0.05)

    assert book.failures(folder) == 0


async def test__disconnect__forgets_what_the_fetch_book_knew_about_the_folder(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack
) -> None:
    await _connected(client, project, remote)
    book = await stack.get(FetchBook)
    book.failed(Path(project["folder"]))

    resp = await client.delete(f"/api/v1/projects/{project['id']}/git/remote")

    assert resp.status_code == 204
    assert book.failures(Path(project["folder"])) == 0


async def test__tick__project_that_is_not_due__does_not_spawn_git_to_read_its_remote(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _connected(client, project, remote)
    reads = 0
    original = GitStoreRemotes.read

    def counting(self: GitStoreRemotes, *args: Any, **kwargs: Any) -> Any:
        nonlocal reads
        reads += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(GitStoreRemotes, "read", counting)

    result = await _tick(stack, Clock())

    assert (result.registered, result.fetched) == (1, 0)
    assert reads == 0


async def test__tick__untrusted_store__is_not_retried_on_every_tick(
    client: AsyncClient, project: dict[str, Any], remote: BareRemote, stack: Stack
) -> None:
    await _connected(client, project, remote)
    (_store(project) / "hooks").mkdir(exist_ok=True)
    (_store(project) / "hooks" / "post-checkout").write_text("#!/bin/sh\n", encoding="utf-8")
    await _age_fetch(stack, project, _PERIOD_PASSED)
    clock = Clock()
    guard_calls = 0
    guard = await stack.get(IGitStoreGuard)
    original = guard.ensure_trusted

    def counting(folder: Path) -> None:
        nonlocal guard_calls
        guard_calls += 1
        original(folder)

    guard.ensure_trusted = counting  # type: ignore[method-assign]

    await _tick(stack, clock)
    await _tick(stack, clock)

    assert guard_calls == 1
