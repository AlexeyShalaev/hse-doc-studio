from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.git_remote.client import (
    DeviceGrant,
    DeviceTokenReply,
    StudioAccount,
    StudioServerError,
    StudioServerTarget,
)
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.infra.git_sync.provider_api import _studio_version
from hse_doc_studio.use_cases.git_sync.studio_servers import (
    LoginState,
    StudioServerLogins,
    StudioServersService,
    normalize_server_url,
    server_url_of,
)


class _Client:
    def __init__(self, replies: list[DeviceTokenReply]) -> None:
        self.replies = replies
        self.targets: list[StudioServerTarget] = []

    async def info(self, target: StudioServerTarget) -> str:
        self.targets.append(target)
        return "0.3.0"

    async def device_code(self, _target: StudioServerTarget, _name: str) -> DeviceGrant:
        return DeviceGrant("hsdv_x", "BCDF-2345", "https://s/device?code=BCDF-2345", 600, 5)

    async def device_token(self, _target: StudioServerTarget, _code: str) -> DeviceTokenReply:
        return self.replies.pop(0)

    async def whoami(self, _target: StudioServerTarget, _token: Secret) -> StudioAccount:
        return StudioAccount("u1", "Анна", ("git:read", "git:write"), None)


class _Credentials:
    def __init__(self) -> None:
        self.items: dict[UUID, tuple[GitCredential, Secret]] = {}

    async def add(self, credential: GitCredential, secret: Secret) -> None:
        self.items[credential.id] = (credential, secret)

    async def list(self) -> list[GitCredential]:
        return [c for c, _ in self.items.values()]


class _Hosts:
    async def get(self, _host: str, _port: int | None) -> None:
        return None


async def _run(replies: list[DeviceTokenReply]) -> tuple[Any, list[float], _Credentials]:
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    credentials = _Credentials()
    service = StudioServersService(_Client(replies), credentials, _Hosts(), StudioServerLogins(), sleep=sleep)  # type: ignore[arg-type]
    login = await service.start_login("https://studio.example.org/", "Студия")
    for _ in range(50):
        state = service.get_login(login.login_id)
        if state.state != LoginState.pending:
            break
        await __import__("asyncio").sleep(0)
    return service.get_login(login.login_id), waits, credentials


async def test__login__slow_down_then_token__saved_as_device_credential() -> None:
    replies = [
        DeviceTokenReply(error="authorization_pending"),
        DeviceTokenReply(error="slow_down"),
        DeviceTokenReply(access_token=Secret("hsd_pat_" + "a" * 32), scope="git:read git:write"),
    ]

    login, waits, credentials = await _run(replies)

    assert login.state == LoginState.approved
    assert waits == [5, 5, 10]
    ((credential, secret),) = credentials.items.values()
    assert (credential.origin, credential.username, credential.host) == ("device", "hse", "studio.example.org")
    assert credential.label == "HSE Doc Studio · studio.example.org"
    assert secret.reveal().startswith("hsd_pat_")


@pytest.mark.parametrize(
    ("error", "state"), [("access_denied", LoginState.denied), ("expired_token", LoginState.expired)]
)
async def test__login__denied_or_expired(error: str, state: str) -> None:
    login, _, credentials = await _run([DeviceTokenReply(error=error)])

    assert login.state == state
    assert credentials.items == {}


def test__normalize_server_url__https_or_loopback_http() -> None:
    assert normalize_server_url("https://Studio.HSE.ru/x", allow_insecure_http=False) == (
        "https://studio.hse.ru",
        "studio.hse.ru",
        None,
    )
    assert normalize_server_url("http://127.0.0.1:17240", allow_insecure_http=False)[0] == "http://127.0.0.1:17240"
    for bad in ("http://studio.hse.ru", "ftp://x", "https://user:pw@x", "nonsense"):
        with pytest.raises(StudioServerError):
            normalize_server_url(bad, allow_insecure_http=False)
    assert normalize_server_url("http://studio.hse.ru", allow_insecure_http=True)[0] == "http://studio.hse.ru"


def test__server_url_of__loopback_http_else_https() -> None:
    def cred(host: str, port: int | None) -> GitCredential:
        return GitCredential(
            uuid4(), GitCredentialKind.pat, "l", host, "hse", CredentialStatus.ok, datetime.now(UTC), port=port
        )

    assert server_url_of(cred("127.0.0.1", 8100)) == "http://127.0.0.1:8100"
    assert server_url_of(cred("studio.hse.ru", None)) == "https://studio.hse.ru"


def test__studio_version__only_studio_info_answer() -> None:
    assert _studio_version(200, {"server": "hse-doc-studio", "version": "0.3.0"}) == ("0.3.0",)
    assert _studio_version(200, {"server": "gitea"}) is None
    assert _studio_version(404, {"server": "hse-doc-studio"}) is None
    assert _studio_version(200, None) is None


def test__credential_repository__origin_round_trip(tmp_path: Path) -> None:
    from hse_doc_studio.infra.git_sync.credential_repository import _from_record, _to_record

    credential = GitCredential(
        uuid4(), GitCredentialKind.pat, "l", "h", "hse", CredentialStatus.ok, datetime.now(UTC), origin="device"
    )
    record = _to_record(credential, "sealed")
    assert _from_record(record).origin == "device"
    record.pop("origin")
    assert _from_record(record).origin is None
