"""Клонирование облачного проекта по адресу (тул MCP clone_cloud_project): разбор адреса, выбор входа, ожидание."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import (
    CloneResult,
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    GitOperation,
    OperationKind,
    OperationStatus,
    SchemaAccess,
)
from hse_doc_studio.use_cases.git_sync.cloud_projects import (
    CloneCloudProjectUC,
    CloudAddressError,
    CloudProjectAddress,
    CloudServerNotConnectedError,
    OpenCloudProjectResult,
    parse_cloud_project_address,
)
from hse_doc_studio.use_cases.mcp.tools.cloud import CloneCloudProjectTool

ANNA = "11111111-1111-4111-8111-111111111111"
SECRET = "hsd_pat_SECRET_TOKEN"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"https://studio.example.org/projects/{ANNA}/", ("studio.example.org", None)),
        (f"https://Studio.Example.org/projects/{ANNA.upper()}/documents/vkr", ("studio.example.org", None)),
        (f"https://studio.example.org:443/git/{ANNA}.git", ("studio.example.org", None)),
        (f"https://studio.example.org:8443/projects/{ANNA}", ("studio.example.org", 8443)),
        (f"http://127.0.0.1:17250/projects/{ANNA}", ("127.0.0.1", 17250)),
    ],
)
def test__parse__project_url__server_and_id(url: str, expected: tuple[str, int | None]) -> None:
    address = parse_cloud_project_address(url, None, None)

    assert (address.host, address.port) == expected
    assert address.project_id == UUID(ANNA)


def test__parse__id_only_or_with_server() -> None:
    assert parse_cloud_project_address(None, ANNA, None) == CloudProjectAddress(UUID(ANNA))
    assert parse_cloud_project_address(None, ANNA, "https://studio.example.org") == CloudProjectAddress(
        UUID(ANNA), "studio.example.org", None
    )
    assert parse_cloud_project_address("https://studio.example.org/", ANNA, None).host == "studio.example.org"


@pytest.mark.parametrize(
    ("url", "project_id"),
    [
        (None, None),
        ("https://studio.example.org/projects/", None),
        ("ftp://studio.example.org/projects/" + ANNA, None),
        (None, "not-a-uuid"),
        ("studio.example.org/projects/" + ANNA, None),
    ],
)
def test__parse__bad_address__rejected(url: str | None, project_id: str | None) -> None:
    with pytest.raises(CloudAddressError):
        parse_cloud_project_address(url, project_id, None)


def test__parse__credentials_in_url__rejected_without_echoing_them() -> None:
    with pytest.raises(CloudAddressError) as raised:
        parse_cloud_project_address(f"https://hse:{SECRET}@studio.example.org/projects/{ANNA}/", None, None)

    assert SECRET not in str(raised.value)


def _credential(host: str, port: int | None = None) -> GitCredential:
    return GitCredential(
        uuid4(),
        GitCredentialKind.pat,
        "l",
        host,
        "hse",
        CredentialStatus.ok,
        datetime.now(UTC),
        port=port,
        origin="device",
    )


class _Servers:
    def __init__(self, *credentials: GitCredential) -> None:
        self.credentials = list(credentials)

    async def device_credentials(self) -> list[GitCredential]:
        return self.credentials


class _Operations:
    def __init__(self) -> None:
        self.items: dict[str, GitOperation] = {}

    def get(self, operation_id: str) -> GitOperation | None:
        return self.items.get(operation_id)


class _Opener:
    """Открытие проекта: проект есть только на перечисленных входах; скачивание завершается по заготовке."""

    def __init__(self, operations: _Operations, *, has: set[UUID], local: bool = False, finish: bool = True) -> None:
        self.operations = operations
        self.has = has
        self.local = local
        self.finish = finish
        self.calls: list[tuple[UUID, UUID]] = []

    async def execute(self, credential_id: UUID, project_id: UUID) -> OpenCloudProjectResult:
        self.calls.append((credential_id, project_id))
        if credential_id not in self.has:
            raise NotFoundError("нет")
        if self.local:
            return OpenCloudProjectResult(project_id, None)
        operation = GitOperation(f"op{len(self.calls)}", OperationKind.clone, None, datetime.now(UTC))
        self.operations.items[operation.id] = operation
        if self.finish:
            done = GitOperation(
                operation.id,
                OperationKind.clone,
                project_id,
                operation.started_at,
                status=OperationStatus.succeeded,
                result=CloneResult(project_id, "/data/projects/ВКР", SchemaAccess.full),
            )
            self.operations.items[operation.id] = done
        return OpenCloudProjectResult(project_id, operation)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def _uc(servers: _Servers, opener: _Opener, operations: _Operations) -> CloneCloudProjectUC:
    clock = _Clock()
    return CloneCloudProjectUC(
        servers,  # type: ignore[arg-type]
        opener,  # type: ignore[arg-type]
        operations,  # type: ignore[arg-type]
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )


async def test__clone__url__uses_the_saved_login_of_that_server_and_waits_for_the_result() -> None:
    other, wanted = _credential("other.example.org"), _credential("studio.example.org")
    operations = _Operations()
    opener = _Opener(operations, has={other.id, wanted.id})

    outcome = await _uc(_Servers(other, wanted), opener, operations).execute(
        parse_cloud_project_address(f"https://studio.example.org/projects/{ANNA}/", None, None), wait_s=30
    )

    assert opener.calls == [(wanted.id, UUID(ANNA))]
    assert (outcome.status, outcome.server_url) == ("succeeded", "https://studio.example.org")


async def test__clone__server_not_connected__no_download() -> None:
    operations = _Operations()
    opener = _Opener(operations, has=set())

    with pytest.raises(CloudServerNotConnectedError) as raised:
        await _uc(_Servers(_credential("other.example.org")), opener, operations).execute(
            CloudProjectAddress(UUID(ANNA), "studio.example.org"), wait_s=0
        )

    assert raised.value.host == "studio.example.org"
    assert opener.calls == []


async def test__clone__id_only__finds_the_server_that_has_the_project() -> None:
    first, second = _credential("a.example.org"), _credential("b.example.org")
    operations = _Operations()
    opener = _Opener(operations, has={second.id})

    outcome = await _uc(_Servers(first, second), opener, operations).execute(CloudProjectAddress(UUID(ANNA)), wait_s=5)

    assert [c for c, _ in opener.calls] == [first.id, second.id]
    assert outcome.server_url == "https://b.example.org"


async def test__clone__nowhere__not_found() -> None:
    operations = _Operations()

    with pytest.raises(NotFoundError):
        await _uc(_Servers(_credential("a.example.org")), _Opener(operations, has=set()), operations).execute(
            CloudProjectAddress(UUID(ANNA)), wait_s=0
        )


async def test__clone__still_downloading_after_wait__running() -> None:
    credential = _credential("studio.example.org")
    operations = _Operations()

    outcome = await _uc(
        _Servers(credential), _Opener(operations, has={credential.id}, finish=False), operations
    ).execute(CloudProjectAddress(UUID(ANNA)), wait_s=3)

    assert outcome.status == "running"


async def test__clone__already_on_the_computer() -> None:
    credential = _credential("studio.example.org")
    operations = _Operations()

    outcome = await _uc(_Servers(credential), _Opener(operations, has={credential.id}, local=True), operations).execute(
        CloudProjectAddress(UUID(ANNA)), wait_s=3
    )

    assert (outcome.status, outcome.operation) == ("already_local", None)


class _Deps:
    def __init__(self, uc: CloneCloudProjectUC) -> None:
        self.uc = uc

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        assert dependency_type is CloneCloudProjectUC
        return self.uc


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=UUID(int=0), model="mcp-client", edit_format=EditFormat.search_replace)


async def test__tool__answer_has_folder_and_no_token() -> None:
    credential = _credential("studio.example.org")
    operations = _Operations()
    tool = CloneCloudProjectTool(_Deps(_uc(_Servers(credential), _Opener(operations, has={credential.id}), operations)))  # type: ignore[arg-type]

    result = await tool.handle(_ctx(), {"url": f"https://studio.example.org/projects/{ANNA}/"})

    assert result.is_error is False, result.text
    assert '"status": "succeeded"' in result.text
    assert "/data/projects/ВКР" in result.text
    assert SECRET not in result.text


async def test__tool__token_in_url__refused_without_echo() -> None:
    operations = _Operations()
    tool = CloneCloudProjectTool(_Deps(_uc(_Servers(), _Opener(operations, has=set()), operations)))  # type: ignore[arg-type]

    result = await tool.handle(_ctx(), {"url": f"https://hse:{SECRET}@studio.example.org/projects/{ANNA}/"})

    assert result.is_error is True
    assert SECRET not in result.text


async def test__tool__not_connected__explains_how_to_connect() -> None:
    operations = _Operations()
    tool = CloneCloudProjectTool(_Deps(_uc(_Servers(), _Opener(operations, has=set()), operations)))  # type: ignore[arg-type]

    result = await tool.handle(_ctx(), {"url": f"https://studio.example.org/projects/{ANNA}/"})

    assert result.is_error is True
    assert result.text.startswith("Сервер studio.example.org не подключён")
    assert "Подключиться к серверу" in result.text or "Connect to a server" in result.text
