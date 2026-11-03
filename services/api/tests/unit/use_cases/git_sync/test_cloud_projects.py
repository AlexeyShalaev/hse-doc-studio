"""Облачные проекты в списке локальной Студии: сбор по входам, сопоставление с локальными, открытие одним шагом."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_remote.client import (
    StudioProject,
    StudioProjectPage,
    StudioServerError,
    StudioServerErrorCode,
    StudioServerTarget,
)
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    GitOperation,
    OperationKind,
    OperationStatus,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.use_cases.git_sync.cloud_projects import (
    CloudOpens,
    ListCloudProjectsUC,
    OpenCloudProjectUC,
    mark_local,
)
from hse_doc_studio.use_cases.git_sync.studio_servers import StudioServerLogins, StudioServersService

pytestmark = pytest.mark.unit

ANNA = "11111111-1111-4111-8111-111111111111"
BORIS = "22222222-2222-4222-8222-222222222222"
CAROL = "33333333-3333-4333-8333-333333333333"


def _project(project_id: str, name: str = "Проект") -> StudioProject:
    return StudioProject(
        id=project_id,
        name=name,
        owner_name="Анна",
        role="owner",
        can_push=True,
        clone_url=f"https://studio.example.org/git/{project_id}.git",
        updated_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


class _Client:
    """Сервер Студии: список проектов по токену, отказ и недоступность по заготовкам."""

    def __init__(self) -> None:
        self.by_token: dict[str, list[StudioProject]] = {}
        self.errors: dict[str, str] = {}
        self.calls: list[tuple[str, int, int]] = []

    async def projects(
        self, _target: StudioServerTarget, token: Secret, *, q: str | None, limit: int, offset: int
    ) -> StudioProjectPage:
        key = token.reveal()
        self.calls.append((key, limit, offset))
        if key in self.errors:
            raise StudioServerError(self.errors[key])
        items = [p for p in self.by_token.get(key, []) if not q or q in p.name]
        return StudioProjectPage(tuple(items[offset : offset + limit]), len(items), limit, offset)


class _Credentials:
    def __init__(self) -> None:
        self.items: dict[UUID, tuple[GitCredential, Secret]] = {}
        self.marked: list[tuple[UUID, CredentialStatus]] = []

    def add(self, host: str, token: str, *, age_days: int = 0, expired: bool = False, origin: str = "device") -> UUID:
        credential = GitCredential(
            uuid4(),
            GitCredentialKind.pat,
            "l",
            host,
            "hse",
            CredentialStatus.ok,
            datetime.now(UTC) - timedelta(days=age_days),
            origin=origin,
            expires_at=datetime(2000, 1, 1, tzinfo=UTC) if expired else None,
        )
        self.items[credential.id] = (credential, Secret(token))
        return credential.id

    async def list(self) -> list[GitCredential]:
        return [c for c, _ in self.items.values()]

    async def get(self, credential_id: UUID) -> GitCredential | None:
        found = self.items.get(credential_id)
        return found[0] if found else None

    async def get_secret(self, credential_id: UUID) -> Secret:
        return self.items[credential_id][1]

    async def mark(self, credential_id: UUID, status: CredentialStatus, **_kw: Any) -> None:
        self.marked.append((credential_id, status))


class _Hosts:
    async def get(self, _host: str, _port: int | None) -> None:
        return None


def _service(client: _Client, credentials: _Credentials) -> StudioServersService:
    return StudioServersService(client, credentials, _Hosts(), StudioServerLogins())  # type: ignore[arg-type]


class _Local:
    def __init__(self, *ids: str) -> None:
        self.ids = ids

    async def execute(self) -> Any:
        return SimpleNamespace(projects=[SimpleNamespace(id=UUID(i)) for i in self.ids])


def test__mark_local__matches_by_server_project_id_ignoring_case() -> None:
    marked = mark_local((_project(ANNA), _project(BORIS)), frozenset({ANNA.upper().lower()}))

    assert [(p.id, p.is_local) for p in marked] == [(ANNA, True), (BORIS, False)]


async def test__list__open_projects_are_marked_not_duplicated() -> None:
    client, credentials = _Client(), _Credentials()
    credentials.add("studio.example.org", "tok-a")
    client.by_token["tok-a"] = [_project(ANNA, "ВКР"), _project(BORIS, "Курсовая")]

    (server,) = await ListCloudProjectsUC(_service(client, credentials), _Local(ANNA)).execute()  # type: ignore[arg-type]

    assert (server.state, server.total) == ("ok", 2)
    assert [(p.name, p.is_local) for p in server.projects] == [("ВКР", True), ("Курсовая", False)]


async def test__list__only_what_the_token_gets_from_the_server() -> None:
    client, credentials = _Client(), _Credentials()
    credentials.add("studio.example.org", "tok-a")
    client.by_token["tok-a"] = [_project(ANNA)]
    client.by_token["tok-other"] = [_project(CAROL)]

    (server,) = await ListCloudProjectsUC(_service(client, credentials), _Local()).execute()  # type: ignore[arg-type]

    assert [p.id for p in server.projects] == [ANNA]


async def test__list__empty_server__ok_with_no_projects() -> None:
    client, credentials = _Client(), _Credentials()
    credentials.add("studio.example.org", "tok-a")

    (server,) = await ListCloudProjectsUC(_service(client, credentials), _Local()).execute()  # type: ignore[arg-type]

    assert (server.state, server.projects, server.total) == ("ok", (), 0)


async def test__list__not_a_device_credential__is_ignored() -> None:
    client, credentials = _Client(), _Credentials()
    credentials.add("github.com", "tok-gh", origin="")
    credentials.add("studio.example.org", "tok-a")

    servers = await ListCloudProjectsUC(_service(client, credentials), _Local()).execute()  # type: ignore[arg-type]

    assert [s.host for s in servers] == ["studio.example.org"]


async def test__list__no_servers__empty() -> None:
    assert await ListCloudProjectsUC(_service(_Client(), _Credentials()), _Local()).execute() == []  # type: ignore[arg-type]


async def test__list__expired_token__state_expired_without_a_request() -> None:
    client, credentials = _Client(), _Credentials()
    credentials.add("studio.example.org", "tok-a", expired=True)

    (server,) = await ListCloudProjectsUC(_service(client, credentials), _Local()).execute()  # type: ignore[arg-type]

    assert (server.state, server.projects) == ("expired", ())
    assert client.calls == []


async def test__list__server_rejects_token__revoked_and_credential_marked() -> None:
    client, credentials = _Client(), _Credentials()
    credential_id = credentials.add("studio.example.org", "tok-a")
    client.errors["tok-a"] = StudioServerErrorCode.unauthorized

    (server,) = await ListCloudProjectsUC(_service(client, credentials), _Local()).execute()  # type: ignore[arg-type]

    assert server.state == "revoked"
    assert credentials.marked == [(credential_id, CredentialStatus.auth_failed)]


async def test__list__server_down__unreachable_and_other_servers_still_listed() -> None:
    client, credentials = _Client(), _Credentials()
    credentials.add("down.example.org", "tok-down")
    credentials.add("studio.example.org", "tok-a")
    client.errors["tok-down"] = StudioServerErrorCode.unreachable
    client.by_token["tok-a"] = [_project(ANNA)]

    servers = await ListCloudProjectsUC(_service(client, credentials), _Local()).execute()  # type: ignore[arg-type]

    assert {s.host: s.state for s in servers} == {"down.example.org": "unreachable", "studio.example.org": "ok"}


async def test__list__relogin__newest_working_token_wins_over_the_stale_one() -> None:
    client, credentials = _Client(), _Credentials()
    credentials.add("studio.example.org", "tok-old", age_days=30)
    credentials.add("studio.example.org", "tok-new")
    client.errors["tok-old"] = StudioServerErrorCode.unauthorized
    client.by_token["tok-new"] = [_project(ANNA)]

    (server,) = await ListCloudProjectsUC(_service(client, credentials), _Local()).execute()  # type: ignore[arg-type]

    assert (server.state, [p.id for p in server.projects]) == ("ok", [ANNA])


async def test__list__newest_token_revoked_older_works__older_is_used() -> None:
    client, credentials = _Client(), _Credentials()
    credentials.add("studio.example.org", "tok-old", age_days=30)
    credentials.add("studio.example.org", "tok-new")
    client.errors["tok-new"] = StudioServerErrorCode.unauthorized
    client.by_token["tok-old"] = [_project(BORIS)]

    (server,) = await ListCloudProjectsUC(_service(client, credentials), _Local()).execute()  # type: ignore[arg-type]

    assert (server.state, [p.id for p in server.projects]) == ("ok", [BORIS])


async def test__list__long_list__is_paged_and_capped() -> None:
    client, credentials = _Client(), _Credentials()
    credentials.add("studio.example.org", "tok-a")
    ids = [str(uuid4()) for _ in range(250)]
    client.by_token["tok-a"] = [_project(i, f"П{n}") for n, i in enumerate(ids)]

    (server,) = await _service(client, credentials).cloud_projects(max_items=150)

    assert (len(server.projects), server.total) == (150, 250)
    assert [offset for _, _, offset in client.calls] == [0, 100]


async def test__find_project__foreign_or_unknown_project__not_found() -> None:
    client, credentials = _Client(), _Credentials()
    credential_id = credentials.add("studio.example.org", "tok-a")
    client.by_token["tok-a"] = [_project(ANNA)]
    service = _service(client, credentials)

    found = await service.find_project(credential_id, UUID(ANNA))
    assert (found.server_url, found.project.name) == ("https://studio.example.org", "Проект")
    with pytest.raises(NotFoundError):
        await service.find_project(credential_id, UUID(CAROL))
    with pytest.raises(NotFoundError):
        await service.find_project(uuid4(), UUID(ANNA))


async def test__find_project__rejected_token__auth_failed() -> None:
    client, credentials = _Client(), _Credentials()
    credential_id = credentials.add("studio.example.org", "tok-a")
    client.errors["tok-a"] = StudioServerErrorCode.unauthorized

    with pytest.raises(GitSyncError) as raised:
        await _service(client, credentials).find_project(credential_id, UUID(ANNA))

    assert raised.value.code == GitErrorCode.auth_failed


class _Operations:
    def __init__(self) -> None:
        self.items: dict[str, GitOperation] = {}

    def get(self, operation_id: str) -> GitOperation | None:
        return self.items.get(operation_id)


class _Clone:
    def __init__(self, operations: _Operations) -> None:
        self.operations = operations
        self.inputs: list[Any] = []

    async def execute(self, inp: Any) -> GitOperation:
        self.inputs.append(inp)
        operation = GitOperation(f"op{len(self.inputs)}", OperationKind.clone, None, datetime.now(UTC))
        self.operations.items[operation.id] = operation
        return operation


class _Defaults:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.names: list[str | None] = []

    async def execute(self, name: str | None) -> Path:
        self.names.append(name)
        return self.root / (name or "project")


def _opener(
    tmp_path: Path, client: _Client, credentials: _Credentials, *local: str
) -> tuple[OpenCloudProjectUC, _Clone, _Defaults, _Operations]:
    operations = _Operations()
    clone, defaults = _Clone(operations), _Defaults(tmp_path)
    uc = OpenCloudProjectUC(
        _service(client, credentials),
        _Local(*local),  # type: ignore[arg-type]
        clone,  # type: ignore[arg-type]
        defaults,  # type: ignore[arg-type]
        operations,  # type: ignore[arg-type]
        CloudOpens(),
    )
    return uc, clone, defaults, operations


async def test__open__project_already_on_the_computer__no_download(tmp_path: Path) -> None:
    client, credentials = _Client(), _Credentials()
    credential_id = credentials.add("studio.example.org", "tok-a")
    uc, clone, _, _ = _opener(tmp_path, client, credentials, ANNA)

    opened = await uc.execute(credential_id, UUID(ANNA))

    assert (opened.project_id, opened.operation) == (UUID(ANNA), None)
    assert clone.inputs == []


async def test__open__new_project__clones_into_the_default_folder_with_the_login(tmp_path: Path) -> None:
    client, credentials = _Client(), _Credentials()
    credential_id = credentials.add("studio.example.org", "tok-a")
    client.by_token["tok-a"] = [_project(ANNA, "ВКР")]
    uc, clone, defaults, _ = _opener(tmp_path, client, credentials)

    opened = await uc.execute(credential_id, UUID(ANNA))

    assert opened.operation is not None
    (inp,) = clone.inputs
    assert inp.url == f"https://studio.example.org/git/{ANNA}.git"
    assert (inp.folder, inp.credential_id, inp.name, inp.insecure_http) == (
        str(tmp_path / "ВКР"),
        credential_id,
        "ВКР",
        False,
    )
    assert defaults.names == ["ВКР"]


async def test__open__second_press_while_downloading__joins_the_same_operation(tmp_path: Path) -> None:
    client, credentials = _Client(), _Credentials()
    credential_id = credentials.add("studio.example.org", "tok-a")
    client.by_token["tok-a"] = [_project(ANNA)]
    uc, clone, _, operations = _opener(tmp_path, client, credentials)

    first = await uc.execute(credential_id, UUID(ANNA))
    again = await uc.execute(credential_id, UUID(ANNA))
    assert first.operation is not None
    assert again.operation is not None
    assert again.operation.id == first.operation.id
    assert len(clone.inputs) == 1

    operations.items[first.operation.id].status = OperationStatus.failed
    retried = await uc.execute(credential_id, UUID(ANNA))
    assert retried.operation is not None
    assert retried.operation.id != first.operation.id


async def test__open__foreign_project__not_found_and_nothing_cloned(tmp_path: Path) -> None:
    client, credentials = _Client(), _Credentials()
    credential_id = credentials.add("studio.example.org", "tok-a")
    client.by_token["tok-a"] = [_project(ANNA)]
    uc, clone, _, _ = _opener(tmp_path, client, credentials)

    with pytest.raises(NotFoundError):
        await uc.execute(credential_id, UUID(CAROL))

    assert clone.inputs == []


async def test__open__loopback_http_server__consent_for_own_computer_only(tmp_path: Path) -> None:
    client, credentials = _Client(), _Credentials()
    credential_id = credentials.add("127.0.0.1", "tok-a")
    client.by_token["tok-a"] = [_project(ANNA)]
    uc, clone, _, _ = _opener(tmp_path, client, credentials)

    await uc.execute(credential_id, UUID(ANNA))

    assert (clone.inputs[0].url, clone.inputs[0].insecure_http) == (f"http://127.0.0.1/git/{ANNA}.git", True)
